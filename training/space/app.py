"""Sokokali Trainer: a private Hugging Face Space that fine-tunes Sokokali's model.

Hardware: the Space starts on free CPU (training disabled). To train, switch it to an
NVIDIA L4 (Settings -> Hardware; needs billing). When training succeeds, the adapter is
pushed to MODEL_REPO and the Space pauses itself, so the GPU stops costing money.

Secrets/variables (Settings -> Variables and secrets):
  HF_TOKEN      write token (secret): reads the private dataset, pushes the model, pauses the Space
  DATASET_REPO  default nyakslamo/sokokali-training
  MODEL_REPO    default nyakslamo/sokokali-qwen3-8b
  BASE_MODEL    default Qwen/Qwen3-8B
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import gradio as gr
from huggingface_hub import HfApi, hf_hub_download, snapshot_download

DATASET_REPO = os.environ.get("DATASET_REPO", "nyakslamo/sokokali-training")
MODEL_REPO = os.environ.get("MODEL_REPO", "nyakslamo/sokokali-qwen3-8b")
BASE_MODEL = os.environ.get("BASE_MODEL", "Qwen/Qwen3-8B")
TOKEN = os.environ.get("HF_TOKEN")
DATA_DIR = Path("/tmp/data")
OUTPUT_DIR = Path("/tmp/outputs/sokokali-lora")
LOG = Path("/tmp/train.log")

_state: dict[str, object] = {"proc": None, "started": None, "finished": None, "exit": None}
_lock = threading.Lock()


def gpu() -> str | None:
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return f"{props.name} ({props.total_memory / 1024**3:.0f} GB)"
    except Exception:  # noqa: BLE001 - torch missing or broken: treat as no GPU
        return None
    return None


def dataset_summary() -> str:
    if not TOKEN:
        return "⚠️ The HF_TOKEN secret is missing: the Space cannot read the private dataset."
    try:
        path = hf_hub_download(DATASET_REPO, "summary.json", repo_type="dataset", token=TOKEN)
        s = json.loads(Path(path).read_text())
        kinds = ", ".join(f"{k} {v}" for k, v in s["by_kind"].items())
        langs = ", ".join(f"{k} {v}" for k, v in s["by_language"].items())
        return f"**{s['train']}** training / **{s['eval']}** evaluation conversations ({kinds}; languages: {langs})"
    except Exception as exc:  # noqa: BLE001
        return f"⚠️ Could not read `{DATASET_REPO}`: {exc}"


def status_md() -> str:
    hardware = gpu()
    return "\n".join(
        [
            f"**Hardware:** {hardware or 'CPU only: training disabled. Switch to an L4 GPU in Settings → Hardware.'}",
            f"**Dataset:** `{DATASET_REPO}`: {dataset_summary()}",
            f"**Base model:** `{BASE_MODEL}` → **trained adapter goes to:** `{MODEL_REPO}` (private)",
        ]
    )


def _watch(proc: subprocess.Popen) -> None:
    code = proc.wait()
    with _lock:
        _state["exit"] = code
        _state["finished"] = time.time()
    with LOG.open("a") as log:
        log.write(f"\n=== training finished with exit code {code} ===\n")
        if code == 0 and os.environ.get("SPACE_ID") and TOKEN:
            log.write("Model pushed. Pausing this Space to stop GPU billing...\n")
            log.flush()
            try:
                HfApi(token=TOKEN).pause_space(os.environ["SPACE_ID"])
            except Exception as exc:  # noqa: BLE001
                log.write(f"Could not pause the Space automatically ({exc}): pause it in Settings.\n")


def start(epochs: float, lr: float, lora_r: int) -> str:
    with _lock:
        proc = _state["proc"]
        if proc is not None and proc.poll() is None:  # type: ignore[union-attr]
            return "Training is already running: see the log below."
        if not gpu():
            return "No GPU on this Space. Switch it to an NVIDIA L4 in Settings → Hardware, then try again."
        if not TOKEN:
            return "Add your Hugging Face write token as the HF_TOKEN secret first."
        snapshot_download(DATASET_REPO, repo_type="dataset", local_dir=DATA_DIR, token=TOKEN)
        cmd = [
            sys.executable, "-u", "finetune_qlora.py",
            "--train", str(DATA_DIR / "train.jsonl"),
            "--eval", str(DATA_DIR / "eval.jsonl"),
            "--base-model", BASE_MODEL,
            "--output", str(OUTPUT_DIR),
            "--hub-repo", MODEL_REPO,
            "--epochs", str(epochs),
            "--lr", str(lr),
            "--lora-r", str(int(lora_r)),
        ]
        LOG.write_text(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} starting: {' '.join(cmd)}\n")
        log = LOG.open("a")
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "HF_TOKEN": TOKEN})
        _state.update(proc=proc, started=time.time(), finished=None, exit=None)
    threading.Thread(target=_watch, args=(proc,), daemon=True).start()
    return f"Training started on {gpu()}. Logs update every few seconds below."


def progress() -> tuple[str, str]:
    text = LOG.read_text(errors="replace")[-20000:] if LOG.exists() else "No training run yet."
    with _lock:
        proc, started, finished, code = _state["proc"], _state["started"], _state["finished"], _state["exit"]
    if proc is None:
        summary = "Idle."
    elif finished is None:
        summary = f"Running for {int((time.time() - started) / 60)} min..."  # type: ignore[operator]
    else:
        summary = "✅ Finished: adapter pushed." if code == 0 else f"❌ Failed (exit code {code}): see the log."
    return summary, text


with gr.Blocks(title="Sokokali Trainer") as demo:
    gr.Markdown("# Sokokali Trainer\nFine-tunes Sokokali's own football-analysis presenter model (QLoRA).")
    status = gr.Markdown(status_md())
    with gr.Row():
        epochs = gr.Slider(1, 3, value=2, step=0.5, label="Epochs")
        lr = gr.Number(value=2e-4, label="Learning rate")
        lora_r = gr.Slider(8, 64, value=16, step=8, label="LoRA rank")
    with gr.Row():
        go = gr.Button("Start training", variant="primary")
        refresh = gr.Button("Refresh status")
    message = gr.Markdown()
    run_state = gr.Markdown("Idle.")
    logs = gr.Textbox(label="Training log", lines=24, max_lines=24, autoscroll=True)

    go.click(start, [epochs, lr, lora_r], message)
    refresh.click(status_md, None, status)
    gr.Timer(5).tick(progress, None, [run_state, logs])
    demo.load(progress, None, [run_state, logs])

if __name__ == "__main__":
    demo.launch()
