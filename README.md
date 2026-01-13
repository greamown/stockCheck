Stock Daily Reporter

Overview
- Subscribe to TW/US tickers via config/subscriptions.json
- Fetch prices, indices, and recent news via yfinance
- Add TW institutional net buy/sell from FinMind (optional)
- Detect earnings-day tickers and highlight reminders
- Send a daily summary through Gemini API and LINE Notify
- Store AI predictions in SQLite for weekly accuracy checks

Setup
1) Create a virtual environment and install dependencies:
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt

2) Copy .env.example to .env and fill in keys.

3) Update config/subscriptions.json with your tickers.
   - TW stocks use .TW (e.g. 2330.TW)
   - US stocks use standard tickers (e.g. AAPL)

Run once
- TW market: python scripts/run_tw.py
- US market: python scripts/run_us.py

Scheduling (cron)
Make sure your system timezone is Asia/Taipei if you want local times.
Example crontab:
  0 14 * * * /path/to/.venv/bin/python /home/adv/stockCheck/scripts/run_tw.py
  0 5  * * * /path/to/.venv/bin/python /home/adv/stockCheck/scripts/run_us.py

Notes
- The AI summary uses Gemini. Set GEMINI_API_KEY.
- LINE Notify requires a token. Set LINE_NOTIFY_TOKEN.
- FinMind (TW institutional data) is optional; set FINMIND_API_KEY to enable.
- SQLite output defaults to data/reports.db; override with REPORT_DB_PATH.
- News comes from yfinance and may be missing for some tickers.
