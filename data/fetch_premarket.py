"""Fetch latest SPY/QQQ quotes via Alpha Vantage GLOBAL_QUOTE endpoint."""

import logging
import time

import requests

AV_BASE_URL = "https://www.alphavantage.co/query"
logger = logging.getLogger(__name__)

PREMARKET_SYMBOLS = [
    {"name": "S&P 500 ETF",    "symbol": "SPY"},
    {"name": "Nasdaq 100 ETF", "symbol": "QQQ"},
]


def fetch_premarket(av_key: str) -> list[dict]:
    """
    Return latest SPY/QQQ quotes from GLOBAL_QUOTE.

    Each dict has: name, symbol, close, change, pct_change,
                   close_fmt, change_fmt, pct_fmt, arrow.
    """
    results = []
    for item in PREMARKET_SYMBOLS:
        symbol = item["symbol"]
        try:
            resp = requests.get(
                AV_BASE_URL,
                params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": av_key},
                timeout=15,
            )
            resp.raise_for_status()
            raw = resp.json()

            if "Information" in raw or "Note" in raw:
                logger.warning(f"AV rate limit on GLOBAL_QUOTE {symbol}")
                results.append(_fallback(item))
                continue

            quote = raw.get("Global Quote", {})
            if not quote or not quote.get("05. price"):
                logger.warning(f"Empty Global Quote for {symbol}")
                results.append(_fallback(item))
                continue

            price = float(quote["05. price"])
            change = float(quote["09. change"])
            pct_change = float(quote["10. change percent"].replace("%", ""))

            results.append({
                "name": item["name"],
                "symbol": symbol,
                "close": price,
                "change": change,
                "pct_change": pct_change,
                "close_fmt": f"${price:,.2f}",
                "change_fmt": f"{change:+,.2f}",
                "pct_fmt": f"{pct_change:+.2f}%",
                "arrow": "\u25b2" if change >= 0 else "\u25bc",
            })

        except Exception as e:
            logger.warning(f"Failed to fetch pre-market {symbol}: {e}")
            results.append(_fallback(item))

        # Respect free-tier rate limit between calls
        if item != PREMARKET_SYMBOLS[-1]:
            time.sleep(15)

    return results


def _fallback(item: dict) -> dict:
    return {
        "name": item["name"],
        "symbol": item["symbol"],
        "close": None,
        "change": None,
        "pct_change": None,
        "close_fmt": "N/A",
        "change_fmt": "N/A",
        "pct_fmt": "N/A",
        "arrow": "",
    }
