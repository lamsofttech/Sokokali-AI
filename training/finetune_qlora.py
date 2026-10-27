"""Fine-tune an open model to be Sokokali (QLoRA), then push it to the Hugging Face Hub.

Runs on a single NVIDIA GPU with ~24 GB (e.g. Colab L4/A100, a Google Cloud G2 VM, Hugging Face).
See training/README.md for the step-by-step guide.

    python training/finetune_qlora.py --train data/training/train.jsonl --eval data/training/eval.jsonl \
        --hub-repo your-org/sokokali-qwen3-8b-lora

What the model learns, per conversation from app.training.dataset:
  1. which tool to call for a question (the assistant's tool-call turn), and
  2. how to turn the tool's real numbers into an expert answer in English, Kiswahili or Sheng.
Loss is computed only on those assistant turns, never on the system prompt, the question or the tool data,
so the model learns to analyse and talk, not to memorise statistics.

--dry-run checks the data formatting with the model's chat template (needs only `transformers`, no GPU).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_BASE = "Qwen/Qwen3-8B"


def load_rows(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def render(tokenizer: Any, messages: list[dict[str, Any]], tools: list[dict[str, Any]], generation_prompt: bool) -> str:
    kwargs: dict[str, Any] = {"tokenize": False, "add_generation_prompt": generation_prompt}
    if "enable_thinking" in (tokenizer.chat_template or ""):
        kwargs["enable_thinking"] = False  # Qwen3: answer directly, no hidden reasoning block
    return tokenizer.apply_chat_template(messages, tools=tools, **kwargs)


def to_prompt_completion(tokenizer: Any, row: dict[str, Any]) -> list[dict[str, str]]:
    """One training pair per assistant turn: everything before it -> that turn.

    The completion is the exact text the chat template produces for the turn, so it includes the model's own
    tool-call syntax. Pairs whose rendering is not a clean prefix extension are skipped (and counted).
    """
    pairs = []
    messages, tools = row["messages"], row.get("tools") or None
    for i, message in enumerate(messages):
        if message["role"] != "assistant":
            continue
        prompt = render(tokenizer, messages[:i], tools, generation_prompt=True)
        full = render(tokenizer, messages[: i + 1], tools, generation_prompt=False)
        if not full.startswith(prompt):
            pairs.append({"prompt": "", "completion": ""})  # marker: skipped
            continue
        pairs.append({"prompt": prompt, "completion": full[len(prompt) :]})
    return pairs


def build_pairs(tokenizer: Any, rows: list[dict[str, Any]]) -> tuple[list[dict[str, str]], int]:
    pairs, skipped = [], 0
    for row in rows:
        for pair in to_prompt_completion(tokenizer, row):
            if pair["prompt"]:
                pairs.append(pair)
            else:
                skipped += 1
    return pairs, skipped


def dry_run(args: argparse.Namespace) -> None:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    rows = load_rows(args.train)[: args.dry_run_rows]
    pairs, skipped = build_pairs(tokenizer, rows)
    lengths = [len(tokenizer(p["prompt"] + p["completion"]).input_ids) for p in pairs]
    print(f"{len(rows)} conversations -> {len(pairs)} training pairs ({skipped} skipped)")
    print(f"tokens per pair: max {max(lengths)}, mean {sum(lengths) // len(lengths)} (max_length is {args.max_length})")
    tool_turn = next((p for p in pairs if "get_" in p["completion"]), None)
    answer_turn = next((p for p in pairs if "get_" not in p["completion"]), None)
    for title, pair in (("TOOL-CALL TURN", tool_turn), ("ANSWER TURN", answer_turn)):
        if pair:
            print(f"\n=== {title}: end of prompt ===\n{pair['prompt'][-300:]}\n=== completion (what is learned) ===\n{pair['completion']}")
    if skipped:
        sys.exit(f"{skipped} turns could not be split cleanly with this chat template")


def train(args: argparse.Namespace) -> None:
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    train_pairs, skipped = build_pairs(tokenizer, load_rows(args.train))
    eval_pairs, _ = build_pairs(tokenizer, load_rows(args.eval)) if args.eval else ([], 0)
    print(f"training pairs: {len(train_pairs)} (skipped {skipped}); eval pairs: {len(eval_pairs)}")

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        ),
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    config = SFTConfig(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        eval_strategy="epoch" if eval_pairs else "no",
        save_strategy="epoch",
        bf16=True,
        gradient_checkpointing=True,
        max_length=args.max_length,
        completion_only_loss=True,  # learn the assistant turns only
        report_to="none",
        seed=args.seed,
    )
    trainer = SFTTrainer(
        model=model,
        args=config,
        train_dataset=Dataset.from_list(train_pairs),
        eval_dataset=Dataset.from_list(eval_pairs) if eval_pairs else None,
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=args.lora_r,
            lora_alpha=2 * args.lora_r,
            lora_dropout=0.05,
            target_modules="all-linear",
            task_type="CAUSAL_LM",
        ),
    )
    trainer.train()
    trainer.save_model(args.output)
    tokenizer.save_pretrained(args.output)
    if eval_pairs:
        print("final eval:", trainer.evaluate())
    if args.hub_repo:
        trainer.model.push_to_hub(args.hub_repo, private=True)
        tokenizer.push_to_hub(args.hub_repo, private=True)
        print(f"pushed LoRA adapter to https://huggingface.co/{args.hub_repo} (private)")


def main() -> None:
    p = argparse.ArgumentParser(description="QLoRA fine-tuning for Sokokali")
    p.add_argument("--train", default="data/training/train.jsonl")
    p.add_argument("--eval", default="data/training/eval.jsonl")
    p.add_argument("--base-model", default=DEFAULT_BASE)
    p.add_argument("--output", default="outputs/sokokali-lora")
    p.add_argument("--hub-repo", default=None, help="e.g. your-org/sokokali-qwen3-8b-lora (pushed as private)")
    p.add_argument("--epochs", type=float, default=2)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--max-length", type=int, default=4096)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--dry-run", action="store_true", help="only check data formatting with the chat template")
    p.add_argument("--dry-run-rows", type=int, default=200)
    args = p.parse_args()
    dry_run(args) if args.dry_run else train(args)


if __name__ == "__main__":
    main()
