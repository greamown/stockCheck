Stock Daily Reporter

Overview
- Subscribe to TW/US tickers via config/subscriptions.json
- Fetch prices, indices, and recent news via yfinance
- Add TW institutional net buy/sell from FinMind (optional)
- Detect earnings-day tickers and highlight reminders
- Send a daily summary through Gemini API and LINE Messaging API
- Store AI predictions in SQLite for weekly accuracy checks

Setup
1) Create a virtual environment and install dependencies:
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   pip install -e .

2) Copy .env.example to .env and fill in keys.

3) Update config/subscriptions.json with your tickers.
   - TW stocks use .TW (e.g. 2330.TW)
   - US stocks use standard tickers (e.g. AAPL)

Run once
- TW market: python scripts/run_reporter.py --market tw
- US market: python scripts/run_reporter.py --market us
- Daily pipeline (prices/news/financials/sentiment): python scripts/run_pipeline.py --market tw
- CLI entrypoints (after install): stockcheck-reporter --market tw, stockcheck-pipeline --market tw

Scheduling (cron)
Make sure your system timezone is Asia/Taipei if you want local times.
Example crontab:
  0 14 * * * /path/to/.venv/bin/python /home/adv/stockCheck/scripts/run_reporter.py --market tw
  0 5  * * * /path/to/.venv/bin/python /home/adv/stockCheck/scripts/run_reporter.py --market us

Notes
- The AI summary uses Gemini (google-genai). Set GEMINI_API_KEY.
- Gemini output length can be limited with GEMINI_MAX_OUTPUT_TOKENS (default 600).
- AI retry settings: AI_MAX_RETRIES and AI_BACKOFF_SEC.
- If Gemini quota is exhausted, it will try OpenRouter (OPENROUTER_API_KEY / OPENROUTER_MODEL).
- OpenRouter timeout: OPENROUTER_TIMEOUT_SEC.
- LINE Messaging API needs LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID (add the bot as a friend to get the user ID).
- Optional Flex messages: set LINE_USE_FLEX=true to send a Flex bubble template.
- LINE push uses `line-bot-sdk`; it's included in requirements.txt.
- FinMind (TW institutional data) is optional; set FINMIND_API_KEY to enable.
- SQLite output defaults to data/reports.db; override with REPORT_DB_PATH.
- yfinance retry settings: YFINANCE_RETRIES and YFINANCE_DELAY_SEC.
- News comes from yfinance and may be missing for some tickers.
- Some sources (SEC/Reddit) require a descriptive HTTP_USER_AGENT.
- Pipeline retry/rate-limit settings: REQUEST_MAX_RETRIES, REQUEST_BACKOFF_SEC, REQUEST_MIN_INTERVAL_SEC.
- Pipeline concurrency: PIPELINE_MAX_WORKERS (default 4).
- Daily report can load pipeline context (news/sentiment/financials) from PIPELINE_DB_PATH if present.
- Data pipeline outputs SQLite to data/market_data.db (override with PIPELINE_DB_PATH).
- Pipeline metadata (CIK, queries) is in config/symbol_metadata.json.
- Source examples: docs/source_examples.md
- Pipeline design: docs/daily_pipeline.md

Get LINE userId (Vercel webhook)
1) Deploy this repo to Vercel (import from GitHub).
2) Set Vercel env var LINE_CHANNEL_SECRET (from LINE Developers).
3) In LINE Developers -> Messaging API, set Webhook URL to:
   https://<your-vercel-domain>/api/line_webhook
4) Enable Webhook and send a message to the bot.
5) Check Vercel logs; it will print: "LINE webhook userIds: Uxxxxxxxx".
