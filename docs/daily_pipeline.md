Daily pipeline design (free / personal research)

Inputs
- Watchlist: config/subscriptions.json
- Optional metadata: config/symbol_metadata.json

Steps (per market)
1) Fetch prices (last 180-220 days)
   - US: Stooq CSV (daily)
   - TW: FinMind (if token), else TWSE/TPEX month APIs
2) Clean and normalize
   - Parse dates to ISO (YYYY-MM-DD)
   - Cast numeric fields to float
   - Drop duplicates and sort by date ascending
3) Compute indicators
   - SMA20, SMA50
   - EMA12, EMA26
   - RSI14
   - MACD (EMA12 - EMA26), signal (EMA9 of MACD), histogram
   - Bollinger bands (20-day, +/- 2 std)
4) Fetch news
   - Google News RSS query by ticker or company name
   - Store title, url, published_at
5) Fetch financials
   - US: SEC EDGAR companyfacts (CIK from config)
   - TW: FinMind financial statements (data_id from config)
6) Fetch social sentiment
   - US: Reddit search or Stocktwits symbol stream
   - TW: PTT Stock board search
7) Store to SQLite
   - price_daily, indicators_daily, news_items, financials, sentiment_items
8) Output daily bundle for AI
   - Load latest prices + indicators + top news + sentiment titles
   - Feed a summary payload into the LLM

Operational notes
- Run once per day (cron), after market close.
- Log all requests and skip sources that are unavailable.
- Store raw JSON payloads for financials to allow reprocessing.
- Keep the pipeline idempotent with primary keys (market, symbol, date).
