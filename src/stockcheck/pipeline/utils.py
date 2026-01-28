import json
import os
import time
from typing import Any, Callable, Dict, Optional

import requests


def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def get_http_headers() -> Dict[str, str]:
    agent = os.getenv("HTTP_USER_AGENT", "stockCheck/1.0 (personal research)")
    return {"User-Agent": agent}


_LAST_REQUEST_TS: Optional[float] = None


def request_with_retry(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
) -> requests.Response:
    max_retries = int(os.getenv("REQUEST_MAX_RETRIES", "3") or 3)
    backoff_sec = float(os.getenv("REQUEST_BACKOFF_SEC", "1.5") or 1.5)
    min_interval = float(os.getenv("REQUEST_MIN_INTERVAL_SEC", "0.5") or 0.5)

    global _LAST_REQUEST_TS
    for attempt in range(1, max_retries + 1):
        if _LAST_REQUEST_TS is not None and min_interval > 0:
            elapsed = time.time() - _LAST_REQUEST_TS
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
        response = requests.get(url, params=params, headers=headers, cookies=cookies, timeout=timeout)
        _LAST_REQUEST_TS = time.time()
        if response.status_code in {429, 500, 502, 503, 504} and attempt < max_retries:
            time.sleep(backoff_sec * (2 ** (attempt - 1)))
            continue
        response.raise_for_status()
        return response
    response.raise_for_status()
    return response


def safe_call(label: str, func: Callable, default, log=None):
    try:
        return func()
    except Exception as exc:
        if log is None:
            print(f"{label} failed: {exc}")
        else:
            log("WARN", f"{label} failed: {exc}")
        return default


def strip_tw_symbol(symbol: str) -> str:
    return symbol.split(".")[0]
