import csv
import html
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup

from .models import PriceRow
from .utils import get_http_headers, request_with_retry, strip_tw_symbol

try:  # optional
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency at runtime
    yf = None


def stooq_symbol(symbol: str) -> str:
    symbol = symbol.lower().strip()
    return f"{symbol}.us"


def fetch_stooq_daily(symbol: str) -> List[PriceRow]:
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol(symbol)}&i=d"
    response = request_with_retry(url, headers=get_http_headers(), timeout=30)
    reader = csv.DictReader(response.text.splitlines())
    rows: List[PriceRow] = []
    for item in reader:
        if not item.get("Date"):
            continue
        rows.append(
            PriceRow(
                date=item["Date"],
                open=float(item.get("Open") or 0.0),
                high=float(item.get("High") or 0.0),
                low=float(item.get("Low") or 0.0),
                close=float(item.get("Close") or 0.0),
                volume=float(item.get("Volume") or 0.0),
                source="stooq",
            )
        )
    return rows


def fetch_finmind_daily(
    symbol: str,
    start_date: date,
    end_date: date,
    token: str,
) -> List[PriceRow]:
    if not token:
        return []
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": strip_tw_symbol(symbol),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "token": token,
    }
    response = request_with_retry(
        "https://api.finmindtrade.com/api/v4/data",
        params=params,
        headers=get_http_headers(),
        timeout=30,
    )
    payload = response.json()
    data = payload.get("data", []) if isinstance(payload, dict) else []
    rows: List[PriceRow] = []
    for item in data:
        rows.append(
            PriceRow(
                date=str(item.get("date", "")),
                open=float(item.get("open") or 0.0),
                high=float(item.get("max") or 0.0),
                low=float(item.get("min") or 0.0),
                close=float(item.get("close") or 0.0),
                volume=float(item.get("Trading_Volume") or item.get("Trading_volume") or 0.0),
                source="finmind",
            )
        )
    return rows


def fetch_yfinance_daily(symbol: str, start_date: date, end_date: date) -> List[PriceRow]:
    if yf is None:
        return []
    end_inclusive = end_date + timedelta(days=1)
    data = yf.download(symbol, start=start_date.isoformat(), end=end_inclusive.isoformat(), progress=False)
    if data.empty:
        return []
    rows: List[PriceRow] = []
    for index, row in data.iterrows():
        rows.append(
            PriceRow(
                date=index.date().isoformat(),
                open=float(row.get("Open") or 0.0),
                high=float(row.get("High") or 0.0),
                low=float(row.get("Low") or 0.0),
                close=float(row.get("Close") or 0.0),
                volume=float(row.get("Volume") or 0.0),
                source="yfinance",
            )
        )
    return rows


def filter_by_date(rows: List[PriceRow], start_date: date, end_date: date) -> List[PriceRow]:
    filtered = []
    for item in rows:
        try:
            item_date = datetime.strptime(item.date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if start_date <= item_date <= end_date:
            filtered.append(item)
    filtered.sort(key=lambda x: x.date)
    return filtered


def parse_rss_items(xml_text: str) -> List[Dict[str, str]]:
    import xml.etree.ElementTree as ET

    items: List[Dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for node in root.findall(".//item"):
        title = node.findtext("title", default="").strip()
        link = node.findtext("link", default="").strip()
        pub = node.findtext("pubDate", default="").strip()
        published_at = ""
        if pub:
            try:
                published_at = parsedate_to_datetime(pub).isoformat()
            except Exception:
                published_at = ""
        items.append({"title": title, "url": link, "published_at": published_at})
    return items


def fetch_google_news(query: str, locale: str) -> List[Dict[str, str]]:
    params = {"q": query}
    if locale == "tw":
        params.update({"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"})
    else:
        params.update({"hl": "en-US", "gl": "US", "ceid": "US:en"})
    response = request_with_retry(
        "https://news.google.com/rss/search",
        params=params,
        headers=get_http_headers(),
        timeout=30,
    )
    return parse_rss_items(response.text)


def fetch_reddit_search(query: str) -> List[Dict[str, str]]:
    params = {
        "q": query,
        "restrict_sr": "1",
        "sort": "new",
        "t": "day",
        "limit": "10",
    }
    response = request_with_retry(
        "https://www.reddit.com/r/stocks/search.json",
        params=params,
        headers=get_http_headers(),
        timeout=30,
    )
    payload = response.json()
    items = []
    for child in payload.get("data", {}).get("children", []):
        data = child.get("data", {})
        items.append(
            {
                "title": data.get("title", ""),
                "url": f"https://www.reddit.com{data.get('permalink', '')}",
                "published_at": datetime.utcfromtimestamp(data.get("created_utc", 0)).isoformat() + "Z",
                "score": float(data.get("score", 0)),
            }
        )
    return items


def fetch_stocktwits(symbol: str) -> List[Dict[str, str]]:
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
    response = request_with_retry(url, headers=get_http_headers(), timeout=30)
    payload = response.json()
    items = []
    for message in payload.get("messages", []):
        items.append(
            {
                "title": message.get("body", ""),
                "url": message.get("url", ""),
                "published_at": message.get("created_at", ""),
                "score": 0.0,
            }
        )
    return items


def fetch_ptt_search(query: str) -> List[Dict[str, str]]:
    url = f"https://www.ptt.cc/bbs/Stock/search?q={query}"
    response = request_with_retry(
        url,
        headers=get_http_headers(),
        cookies={"over18": "1"},
        timeout=30,
    )
    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    for entry in soup.select("div.r-ent a"):
        link = entry.get("href", "")
        title = entry.get_text(strip=True)
        if not link or not title:
            continue
        if not link.startswith("/bbs/Stock/"):
            continue
        items.append(
            {
                "title": html.unescape(title),
                "url": f"https://www.ptt.cc{link}",
                "published_at": "",
                "score": 0.0,
            }
        )
    return items[:10]


def fetch_sec_companyfacts(cik: str) -> Dict[str, Any]:
    cik = cik.zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    response = request_with_retry(url, headers=get_http_headers(), timeout=30)
    return response.json()


def fetch_finmind_financials(symbol: str, start_date: date, end_date: date, token: str) -> Dict[str, Any]:
    if not token:
        return {}
    params = {
        "dataset": "TaiwanStockFinancialStatements",
        "data_id": strip_tw_symbol(symbol),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "token": token,
    }
    response = request_with_retry(
        "https://api.finmindtrade.com/api/v4/data",
        params=params,
        headers=get_http_headers(),
        timeout=30,
    )
    return response.json()


def get_symbol_query(symbol: str, metadata: Dict[str, Any], market: str) -> str:
    entry = metadata.get(market, {}).get(symbol, {})
    return entry.get("query") or f"{symbol} stock"


def get_symbol_cik(symbol: str, metadata: Dict[str, Any]) -> str:
    entry = metadata.get("us", {}).get(symbol, {})
    return entry.get("cik", "")


def get_finmind_id(symbol: str, metadata: Dict[str, Any]) -> str:
    entry = metadata.get("tw", {}).get(symbol, {})
    return entry.get("finmind_id", strip_tw_symbol(symbol))
