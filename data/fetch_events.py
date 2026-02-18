"""Fetch economic calendar and earnings from Finnhub."""

import logging
from datetime import date, datetime, timedelta

import requests

FH_BASE_URL = "https://finnhub.io/api/v1"
logger = logging.getLogger(__name__)

# Countries to include in economic event output
COUNTRIES_OF_INTEREST = {"US", "EU", "GB", "JP", "CN"}


def _is_relevant(event: dict) -> bool:
    """Keep only high/medium impact events from key countries."""
    country = event.get("country", "").upper()
    impact = event.get("impact", "").lower()
    return country in COUNTRIES_OF_INTEREST and impact in ("high", "medium")


def _fmt_val(val, unit: str = "") -> str:
    if val is None:
        return "\u2014"
    if isinstance(val, float):
        return f"{val:,.2f}{unit}"
    return f"{val}{unit}"


def _parse_events(raw_list: list) -> list[dict]:
    out = []
    for ev in raw_list:
        if not _is_relevant(ev):
            continue
        time_raw = ev.get("time", "")
        try:
            time_str = datetime.strptime(time_raw, "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
        except Exception:
            time_str = time_raw[:10] if time_raw else "\u2014"

        unit = ev.get("unit", "")
        out.append({
            "time_str": time_str,
            "event": ev.get("event", ""),
            "country": ev.get("country", ""),
            "actual": ev.get("actual"),
            "estimate": ev.get("estimate"),
            "prev": ev.get("prev"),
            "impact": ev.get("impact", "").upper(),
            "unit": unit,
            "actual_str": _fmt_val(ev.get("actual"), unit),
            "estimate_str": _fmt_val(ev.get("estimate"), unit),
            "prev_str": _fmt_val(ev.get("prev"), unit),
        })
    return out


def fetch_events_last24h(fh_key: str, as_of: datetime) -> list[dict]:
    """Return economic events released in the last 24 hours."""
    yesterday = (as_of - timedelta(days=1)).strftime("%Y-%m-%d")
    today = as_of.strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            f"{FH_BASE_URL}/calendar/economic",
            params={"from": yesterday, "to": today, "token": fh_key},
            timeout=15,
        )
        resp.raise_for_status()
        return _parse_events(resp.json().get("economicCalendar", []))
    except Exception as e:
        logger.warning(f"Failed to fetch Finnhub last-24h events: {e}")
        return []


def fetch_day_ahead(fh_key: str, today: date) -> dict:
    """Return today's economic events and top earnings releases."""
    today_str = today.strftime("%Y-%m-%d")
    events = []
    earnings = []

    # Economic calendar
    try:
        resp = requests.get(
            f"{FH_BASE_URL}/calendar/economic",
            params={"from": today_str, "to": today_str, "token": fh_key},
            timeout=15,
        )
        resp.raise_for_status()
        events = _parse_events(resp.json().get("economicCalendar", []))
    except Exception as e:
        logger.warning(f"Failed to fetch Finnhub day-ahead events: {e}")

    # Earnings calendar
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

    return {"events": events, "earnings": earnings}
