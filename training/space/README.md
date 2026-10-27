---
title: Sokokali Trainer
emoji: ⚽
colorFrom: green
colorTo: red
sdk: gradio
sdk_version: 6.30.0
app_file: app.py
pinned: false
---

# Sokokali Trainer

Private Space that fine-tunes Sokokali's football-analysis presenter model with QLoRA.

1. **Settings → Hardware:** choose **Nvidia L4** (requires billing on your account). The Space shows "CPU only" until then.
2. **Settings → Variables and secrets:** `HF_TOKEN` must be set (write token). Optional variables: `DATASET_REPO`, `MODEL_REPO`, `BASE_MODEL`.
3. Press **Start training** and watch the log. When it finishes, the adapter is pushed to the private model repo and the Space **pauses itself** to stop GPU billing.

Source: `training/space` in the Sokokali-AI repository. The training script `finetune_qlora.py` is copied from `training/`.
