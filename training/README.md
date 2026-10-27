# Training Sokokali's own model

Goal: an open model, fine-tuned to be Sokokali. It knows how to analyse football history and talk about it in English, Kiswahili and Sheng, and it always takes numbers from Sokokali's tools (the historical database and your analysts' picks), never from memory.

```
Historical database (12,774 EPL matches, 1993/94 -> today)
        │  python -m app.training.dataset
        ▼
data/training/train.jsonl + eval.jsonl   (question -> tool call -> real numbers -> expert answer, 3 languages)
        │  training/finetune_qlora.py   (QLoRA on one GPU)
        ▼
Hugging Face Hub (private): your-org/sokokali-qwen3-8b-lora
        │  (next step) serve it and plug it into Sokokali next to Claude
        ▼
Sokokali on air
```

## 1. Build the dataset (on your computer, with Docker running)

```powershell
cd "C:\Users\Local User\Desktop\SOKO"
docker compose exec backend python -m app.history.ingest                 # update the historical data (fast after the first run)
docker compose exec backend python -m app.training.dataset --out data/training
docker compose cp backend:/app/data/training ./data/training
```

`data/training/summary.json` shows the counts. Every numeric answer is checked against its tool result (the same grounding check as the live app); `rejected_ungrounded` must be 0.

Options: `--per-pair 4` (more head-to-head examples), `--per-team 12`, `--guardrails 300`.

Optional format check (no GPU needed). It renders the conversations with the model's chat template and shows exactly what will be learned:

```powershell
python -m venv training\.venv
training\.venv\Scripts\python.exe -m pip install "transformers>=4.51,<5" jinja2
training\.venv\Scripts\python.exe training\finetune_qlora.py --dry-run
```

## 2. Put the dataset on Hugging Face (private)

Create a free account at https://huggingface.co and an access token with **write** permission (Settings, then Access Tokens). Then:

```powershell
training\.venv\Scripts\python.exe -m pip install huggingface_hub
training\.venv\Scripts\python.exe -c "from huggingface_hub import HfApi; api=HfApi(token='hf_...'); api.create_repo('YOUR-NAME/sokokali-training', repo_type='dataset', private=True, exist_ok=True); api.upload_folder(folder_path='data/training', repo_id='YOUR-NAME/sokokali-training', repo_type='dataset')"
```

Keep repos **private**. The dataset is built from football-data.co.uk data. Check their terms before any commercial use or public release.

## Already set up on Hugging Face (account `nyakslamo`, all private)

- Dataset: https://huggingface.co/datasets/nyakslamo/sokokali-training
- Model repo: https://huggingface.co/nyakslamo/sokokali-qwen3-8b (filled by the first training run)
- **Easiest way to train:** open [`training/sokokali_colab.ipynb`](sokokali_colab.ipynb) in Google Colab (File → Open notebook → GitHub → `lamsofttech/Sokokali-AI`) and run the cells. The free T4 trains `Qwen3-4B`; Colab Pro (L4/A100) trains `Qwen3-8B`. Checkpoints go to Google Drive, so a disconnect does not lose progress.
- A trainer **Space** (`training/space/`) is ready, but Hugging Face requires a **PRO** subscription to host it (plus billing for the GPU). Once subscribed, it can be published with one command.

## 3. Train on a GPU

You need one NVIDIA GPU with about 24 GB of memory. This computer has none, which is normal. Options:

- **Google Colab** (quickest to try): Runtime, then Change runtime type, then an **L4** or **A100** GPU (Colab Pro).
- **Google Cloud** (matches the deployment plan): a G2 VM with an L4 GPU, or a Vertex AI custom training job.
- **Hugging Face**: a GPU Space or a paid compute option.

In a Colab notebook (or a terminal on the GPU machine):

```bash
git clone https://github.com/lamsofttech/Sokokali-AI.git && cd Sokokali-AI
pip install -r training/requirements.txt
huggingface-cli login            # paste your write token
python -c "from huggingface_hub import snapshot_download; snapshot_download('YOUR-NAME/sokokali-training', repo_type='dataset', local_dir='data/training')"
python training/finetune_qlora.py \
    --train data/training/train.jsonl --eval data/training/eval.jsonl \
    --base-model Qwen/Qwen3-8B \
    --hub-repo YOUR-NAME/sokokali-qwen3-8b-lora
```

The current dataset has about 3,200 training pairs, about 2,100 tokens each. Two epochs should take on the order of an hour or two on an L4/A100, but measure it on your first run. The result is a small **LoRA adapter** (tens to hundreds of MB), pushed privately to your Hub repo.

### Choosing the base model

| Model | License | Notes |
|---|---|---|
| `Qwen/Qwen3-8B` (default) | Apache-2.0, open | Strong multilingual and tool calling; the script disables its "thinking" mode |
| `Qwen/Qwen2.5-7B-Instruct` | Apache-2.0, open | Proven alternative; dataset verified with its template too |
| `google/gemma-3-12b-it` | Gemma licence, gated | Accept the licence on Hugging Face first; needs more GPU memory |
| `meta-llama/Llama-3.1-8B-Instruct` | Llama licence, gated | Accept the licence first |
| `Jacaranda/UlizaLlama` | No licence stated | Kiswahili-adapted Llama; clarify licensing with its authors before commercial use |

Before committing to one, compare two or three on your own Kiswahili and Sheng questions (see step 4). Sheng is weak in all of them, so your own conversation data matters most.

## 4. Evaluate before using it on air

`eval.jsonl` is a fixed held-out set (re-runs keep the same split). A fine-tuned model is good enough to switch on when:

1. It calls the **right tool with the right teams** on the evaluation questions.
2. Its answers pass the **grounding check**: no number that isn't in the tool result.
3. Its Kiswahili and Sheng read naturally to your team, judged by people on a sample.
4. It still refuses "sure bet" and "fixed match" requests.

Sokokali keeps Claude and the rule-based engine as fallbacks, so the switch can be gradual.

## 5. Keep improving it

Each training round:

- Add **real conversations** from the broadcast log (`/api/v1/history/broadcast`), with usernames and personal data removed. Kenya's Data Protection Act applies: tell viewers their comments may be used to improve Sokokali.
- Add **your analysts' written explanations** of their picks. They are the best examples of how an expert reasons.
- Rebuild the dataset after each matchweek (`ingest` then `dataset`), retrain, evaluate, and keep the version only if it scores better.

Note on Claude: Anthropic's commercial terms restrict using Claude's outputs to train other models. This dataset is built from the historical data and Sokokali's own templates, not from Claude. Check Anthropic's terms before adding Claude-written conversations to it.
