# Ledgerly: Personal Finance Advisor Bot

A focused Flask + SQLAlchemy starter for income tracking, expense categorization, savings visibility, and AI-ready financial guidance.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open `http://127.0.0.1:5000`. The dashboard works without an AI key using a deterministic recommendation fallback. Keep API keys in `.env`; the Gemini integration point is `build_advice` in `app.py`.