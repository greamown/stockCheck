Source API examples (free or freemium)

Prices
- US (Stooq CSV, daily):
  https://stooq.com/q/d/l/?s=aapl.us&i=d
  https://stooq.com/q/d/l/?s=msft.us&i=d
- TW (TWSE daily, month-based, JSON):
  https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=20240101&stockNo=2330
- TW (TPEX daily, month-based, JSON):
  https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php?response=json&date=2024/01/01&code=6488
- TW (FinMind daily, JSON; token required):
  https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id=2330&start_date=2024-01-01&end_date=2024-02-01&token=YOUR_TOKEN

News
- Google News RSS (search query):
  https://news.google.com/rss/search?q=AAPL%20stock&hl=en-US&gl=US&ceid=US:en
  https://news.google.com/rss/search?q=TSMC%20stock&hl=en-US&gl=US&ceid=US:en
- GDELT 2.1 (JSON):
  https://api.gdeltproject.org/api/v2/doc/doc?query=AAPL%20stock&mode=ArtList&maxrecords=10&format=json

Financials
- US SEC EDGAR company facts (JSON; CIK required, set User-Agent):
  https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json
- TW FinMind financials (JSON; token required):
  https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id=2330&start_date=2023-01-01&end_date=2024-01-01&token=YOUR_TOKEN

Social sentiment
- Reddit search JSON (public, set User-Agent):
  https://www.reddit.com/r/stocks/search.json?q=TSLA&restrict_sr=1&sort=new&t=day&limit=10
- Stocktwits stream (JSON, no key):
  https://api.stocktwits.com/api/2/streams/symbol/AAPL.json
- PTT Stock board search (HTML):
  https://www.ptt.cc/bbs/Stock/search?q=2330

Notes
- Always check each provider's Terms of Service, rate limits, and robots.txt.
- Some endpoints are month-based (TWSE/TPEX) and need date iteration.
- SEC EDGAR requires a descriptive User-Agent string.
