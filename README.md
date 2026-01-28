# Stock Daily Reporter

## What it does
- Collects TW/US market data (prices, news, optional financials/sentiment)
- Builds a daily summary and sends it to LINE
- Stores results in SQLite for later review

## Quick start
1) Create venv and install:

   ```bash
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   pip install -e .
   ```

2) Copy environment file:

   ```bash
   cp .env.example .env
   ```

3) Update subscriptions:

   Edit `config/subscriptions.json`:
   - TW stocks use `.TW` (example: `2330.TW`)
   - US stocks use standard tickers (example: `AAPL`)

## Run once (reporter)
```bash
python scripts/run_reporter.py --market tw
python scripts/run_reporter.py --market us
```

## Run once (pipeline)
```bash
python scripts/run_pipeline.py --market tw
python scripts/run_pipeline.py --market us
```

## CLI entrypoints (after install)
```bash
stockcheck-reporter --market tw
stockcheck-pipeline --market tw
```

## Scheduling (cron)
Set timezone to Asia/Taipei if you want local times.
Example:

```cron
0 14 * * * /path/to/.venv/bin/python /path/to/stockCheck/scripts/run_reporter.py --market tw
0 5  * * * /path/to/.venv/bin/python /path/to/stockCheck/scripts/run_reporter.py --market us
```

## Environment variables
### Core
- GEMINI_API_KEY (required for AI summary)
- GEMINI_MODEL (optional)
- LINE_CHANNEL_ACCESS_TOKEN (required for LINE push)
- LINE_USER_ID (required for LINE push)

### Optional
- FINMIND_API_KEY (TW institutional data)
- REPORT_DB_PATH (default: data/reports.db)
- PIPELINE_DB_PATH (default: data/market_data.db)
- LINE_USE_FLEX (true to send Flex messages)
- HTTP_USER_AGENT (recommended for SEC/Reddit)

## AI settings
- GEMINI_MAX_OUTPUT_TOKENS (default 600)
- AI_MAX_RETRIES, AI_BACKOFF_SEC
- OPENROUTER_API_KEY, OPENROUTER_MODEL (fallback if Gemini quota)
- OPENROUTER_TIMEOUT_SEC

## Pipeline settings
- REQUEST_MAX_RETRIES, REQUEST_BACKOFF_SEC, REQUEST_MIN_INTERVAL_SEC
- PIPELINE_MAX_WORKERS (default 4)
- Pipeline metadata: config/symbol_metadata.json

## Docs
- Pipeline design: docs/daily_pipeline.md
- Source examples: docs/source_examples.md

## Get LINE userId (Vercel webhook)
1) Deploy this repo to Vercel.
2) Set LINE_CHANNEL_SECRET in Vercel env vars.
3) Set Webhook URL in LINE Developers:
   `https://<your-vercel-domain>/api/line_webhook`
4) Enable webhook and message the bot.
5) Check Vercel logs for:
   `LINE webhook userIds: Uxxxxxxxx`
