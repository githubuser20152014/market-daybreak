"""Fetch earnings calendar from Finnhub."""

import logging
from datetime import date

import requests

FH_BASE_URL = "https://finnhub.io/api/v1"
logger = logging.getLogger(__name__)


def fetch_day_ahead(fh_key: str, today: date) -> dict:
    """Return today's earnings releases (top 10)."""
    today_str = today.strftime("%Y-%m-%d")
    earnings = []
    try:
        resp = requests.get(
            f"{FH_BASE_URL}/calendar/earnings",
            params={"from": today_str, "to": today_str, "token": fh_key},
            timeout=15,
        )
        resp.raise_for_status()
        for e in resp.json().get("earningsCalendar", [])[:10]:
            eps = e.get("epsEstimate")
            rev = e.get("revenueEstimate")
            hour = e.get("hour", "")
            when = "Pre-mkt" if hour == "bmo" else "After-mkt" if hour == "amc" else "TBD"
            earnings.append({
                "symbol": e.get("symbol", ""),
                "eps_str": f"${eps:.2f}" if eps is not None else "\u2014",
                "rev_str": f"${rev / 1e9:.1f}B" if rev else "\u2014",
                "when": when,
            })
    except Exception as e:
        logger.warning(f"Failed to fetch Finnhub earnings: {e}")

    return {"earnings": earnings}
