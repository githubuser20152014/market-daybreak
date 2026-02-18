"""Fetch EOD market data from Alpha Vantage with file-based caching."""

import json
import logging
import time
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).parent / "cache"
AV_BASE_URL = "https://www.alphavantage.co/query"
RATE_LIMIT_SLEEP = 15  # seconds between API calls (free tier: ~4 req/min to be safe)

logger = logging.getLogger(__name__)


def _cache_path(symbol: str, trade_date: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{symbol}_{trade_date}.json"


def _load_cache(symbol: str, trade_date: str) -> dict | None:
    path = _cache_path(symbol, trade_date)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _save_cache(symbol: str, trade_date: str, data: dict) -> None:
    path = _cache_path(symbol, trade_date)
    with open(path, "w") as f:
        json.dump(data, f)


def fetch_symbol(symbol: str, trade_date: str, api_key: str, sleep: bool = True) -> dict:
    """
    Fetch EOD data for a single symbol on trade_date.

    Returns dict with keys: symbol, close, prev_close, change, pct_change
    Raises ValueError on API error responses.
    """
    cached = _load_cache(symbol, trade_date)
    if cached:
        logger.debug(f"Cache hit: {symbol} {trade_date}")
        return cached

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": "compact",
        "apikey": api_key,
    }
    resp = requests.get(AV_BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    raw = resp.json()

    # Detect API-level errors (rate limit, bad symbol, etc.)
    if "Information" in raw:
        raise ValueError(f"Alpha Vantage rate limit/info: {raw['Information']}")
    if "Note" in raw:
        raise ValueError(f"Alpha Vantage note: {raw['Note']}")
    if "Error Message" in raw:
        raise ValueError(f"Alpha Vantage error: {raw['Error Message']}")

    ts = raw.get("Time Series (Daily)", {})
    if not ts:
        raise ValueError(f"No time series data returned for {symbol}")

    dates = sorted(ts.keys(), reverse=True)

    # Find the target trade_date entry
    if trade_date not in ts:
        # Fall back to most recent available date
        target_date = dates[0]
        logger.warning(f"{symbol}: {trade_date} not in data, using {target_date}")
    else:
        target_date = trade_date

    target_idx = dates.index(target_date)
    entry = ts[target_date]
    close = float(entry["4. close"])

    # Previous day for % change (using unadjusted close — fine for ETFs intraday)
    if target_idx + 1 < len(dates):
        prev_entry = ts[dates[target_idx + 1]]
        prev_close = float(prev_entry["4. close"])
        change = close - prev_close
        pct_change = (change / prev_close) * 100
    else:
        prev_close = None
        change = None
        pct_change = None

    result = {
        "symbol": symbol,
        "close": close,
        "prev_close": prev_close if target_idx + 1 < len(dates) else None,
        "change": change,
        "pct_change": pct_change,
        "date": target_date,
    }

    _save_cache(symbol, trade_date, result)
    logger.debug(f"Fetched & cached: {symbol} {trade_date}")

    if sleep:
        time.sleep(RATE_LIMIT_SLEEP)

    return result


def fetch_all_markets(trade_date: str, api_key: str, indices: list[dict]) -> list[dict]:
    """
    Fetch all indices, returning a list of row dicts (with None values on failure).
    Sleeps between API calls only on cache misses.
    """
    rows = []
    for i, idx in enumerate(indices):
        symbol = idx["symbol"]
        name = idx["name"]
        group = idx["group"]

        # Sleep after live API calls (handled inside fetch_symbol when sleep=True)
        # Only skip sleep when data comes from cache
        is_cached = _load_cache(symbol, trade_date) is not None
        try:
            data = fetch_symbol(symbol, trade_date, api_key, sleep=not is_cached)
            rows.append({
                "name": name,
                "symbol": symbol,
                "group": group,
                "close": data["close"],
                "change": data["change"],
                "pct_change": data["pct_change"],
            })
        except Exception as e:
            logger.warning(f"Failed to fetch {symbol} ({name}): {e}")
            rows.append({
                "name": name,
                "symbol": symbol,
                "group": group,
                "close": None,
                "change": None,
                "pct_change": None,
            })

    return rows
