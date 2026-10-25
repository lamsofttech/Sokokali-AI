# Sokokali Starter

Local prototype only. No TikTok integration, external LLM, live data, or calibrated betting predictions.

## Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Enter `demo` for a hypothetical football probability calculation.

## Optional API

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

Visit http://127.0.0.1:8000/docs and try POST /chat or POST /predict-demo.

Do not expose the development API publicly. Production requires authentication, moderation, logging, rate limits, and deployment security.
