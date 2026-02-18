#!/usr/bin/env python3
"""
Market Daybreak — Daily pre-market report generator.

Usage:
    python generate_daybreak.py                  # Generate today's report
    python generate_daybreak.py --run-at 07:00   # Simulate specific time
    python generate_daybreak.py --preview        # Print without saving
"""

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import anthropic
import markdown as md_lib
import pytz
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from data.fetch_global_markets import fetch_all_markets
from data.send_email import send_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

EASTERN = pytz.timezone("America/New_York")
BASE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Date logic
# ---------------------------------------------------------------------------

def get_prior_trading_day(dt: datetime) -> date:
    """Return the most recent trading day before dt (skips weekends and US market holidays)."""
    # US market holidays — updated annually as needed
    US_MARKET_HOLIDAYS = {
        # 2026
        date(2026, 1, 1),   # New Year's Day
        date(2026, 1, 19),  # MLK Day
        date(2026, 2, 16),  # Presidents' Day
        date(2026, 4, 3),   # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),   # Independence Day (observed)
        date(2026, 9, 7),   # Labor Day
        date(2026, 11, 26), # Thanksgiving
        date(2026, 12, 25), # Christmas
        # 2025
        date(2025, 1, 1),
        date(2025, 1, 20),
        date(2025, 2, 17),
        date(2025, 4, 18),
        date(2025, 5, 26),
        date(2025, 6, 19),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
    }

    d = dt.date() - timedelta(days=1)  # start from yesterday
    while d.weekday() >= 5 or d in US_MARKET_HOLIDAYS:
        d -= timedelta(days=1)
    return d


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_close(val) -> str:
    if val is None:
        return "N/A"
    return f"${val:,.2f}"


def fmt_change(val) -> str:
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:,.2f}"


def fmt_pct(val) -> str:
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def arrow(val) -> str:
    if val is None:
        return ""
    return "▲" if val >= 0 else "▼"


# ---------------------------------------------------------------------------
# Claude narrative generation
# ---------------------------------------------------------------------------

def call_claude(market_rows: list[dict], api_key: str) -> dict:
    """
    Call Claude Haiku to generate Morning Brief and Positioning Tips.
    Returns dict with 'morning_brief' and 'positioning_tips' keys.
    """
    # Build a compact market summary for the prompt
    lines = []
    for row in market_rows:
        pct = f"{row['pct_change']:+.2f}%" if row["pct_change"] is not None else "N/A"
        lines.append(f"  - {row['name']} ({row['symbol']}): {fmt_close(row['close'])} ({pct})")
    market_summary = "\n".join(lines)

    prompt = f"""You are a concise financial analyst writing a pre-market briefing for serious US traders.

Yesterday's market closes:
{market_summary}

Write two sections:

MORNING_BRIEF:
A 3–4 sentence narrative summary of yesterday's market action. Mention the major moves, any notable divergences between US/Europe/Asia, and set the tone for today. Be factual and professional. Do not use bullet points.

POSITIONING_TIPS:
A markdown table with exactly this header and 3–5 data rows:
| Signal | Action | Rationale |
|--------|--------|-----------|
Use real ETF tickers (SPY, QQQ, DIA, EWG, EWJ, GLD, TLT, etc.). Keep each cell concise (under 12 words). Base tips on the actual market data provided.

Output ONLY the two sections above with their labels. No preamble or extra commentary."""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Parse sections
    if "POSITIONING_TIPS:" in raw:
        parts = raw.split("POSITIONING_TIPS:", 1)
        morning_brief = parts[0].replace("MORNING_BRIEF:", "").strip()
        positioning_tips = parts[1].strip()
    else:
        # Fallback: treat whole response as morning brief
        morning_brief = raw.replace("MORNING_BRIEF:", "").strip()
        positioning_tips = (
            "| Signal | Action | Rationale |\n"
            "|--------|--------|-------|\n"
            "| *Data unavailable* | — | — |"
        )

    return {"morning_brief": morning_brief, "positioning_tips": positioning_tips}


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def build_market_rows(raw_rows: list[dict]) -> list[dict]:
    """Add formatted display fields to each market row."""
    result = []
    for row in raw_rows:
        result.append({
            **row,
            "close_fmt": fmt_close(row["close"]),
            "change_fmt": fmt_change(row["change"]),
            "pct_fmt": fmt_pct(row["pct_change"]),
            "arrow": arrow(row["change"]),
        })
    return result


def render_report(context: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(BASE_DIR / "templates")),
        keep_trailing_newline=True,
    )
    template = env.get_template("daybreak_template.jinja2")
    return template.render(**context)


def render_pdf(context: dict, output_path: Path) -> None:
    """Render a styled PDF using the reference newsletter design (daybreak_pdf.html)."""
    # Split morning brief into paragraphs for individual <p> tags
    morning_brief_paras = [
        p.strip() for p in context["morning_brief"].split("\n\n") if p.strip()
    ]

    # Convert Claude's markdown positioning-tips table → HTML
    converter = md_lib.Markdown(extensions=["tables"])
    positioning_tips_html = converter.convert(context["positioning_tips"])

    pdf_context = {
        **context,
        "morning_brief_paras": morning_brief_paras,
        "positioning_tips_html": positioning_tips_html,
    }

    env = Environment(
        loader=FileSystemLoader(str(BASE_DIR / "templates")),
        keep_trailing_newline=True,
    )
    html = env.get_template("daybreak_pdf.html").render(**pdf_context)

    with open(output_path, "wb") as f:
        result = pisa.CreatePDF(html, dest=f)
    if result.err:
        raise RuntimeError(f"PDF generation failed ({result.err} errors)")


def render_email_html(context: dict) -> str:
    """Render the email HTML body using the email-optimised Jinja2 template."""
    morning_brief_paras = [
        p.strip() for p in context["morning_brief"].split("\n\n") if p.strip()
    ]
    converter = md_lib.Markdown(extensions=["tables"])
    positioning_tips_html = converter.convert(context["positioning_tips"])

    email_context = {
        **context,
        "morning_brief_paras": morning_brief_paras,
        "positioning_tips_html": positioning_tips_html,
    }
    env = Environment(
        loader=FileSystemLoader(str(BASE_DIR / "templates")),
        keep_trailing_newline=True,
    )
    return env.get_template("daybreak_email.html").render(**email_context)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_dotenv()

    import os
    av_key = os.getenv("ALPHAVANTAGE_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    missing = []
    if not av_key:
        missing.append("ALPHAVANTAGE_API_KEY")
    if not anthropic_key:
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your API keys.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Generate Market Daybreak report")
    parser.add_argument(
        "--run-at",
        metavar="HH:MM",
        help="Simulate generation at a specific EST time (e.g. 07:00)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print report to stdout without saving",
    )
    args = parser.parse_args()

    now_eastern = datetime.now(EASTERN)
    trade_date = get_prior_trading_day(now_eastern)
    trade_date_str = trade_date.strftime("%Y-%m-%d")
    report_date = now_eastern.strftime("%A, %B %d, %Y").replace(" 0", " ")

    if args.run_at:
        generated_at = args.run_at
    else:
        generated_at = now_eastern.strftime("%I:%M %p")

    # Load index config
    config_path = BASE_DIR / "config" / "indices.json"
    with open(config_path) as f:
        indices = json.load(f)

    # Fetch market data
    logger.info(f"Fetching market data for {trade_date_str}...")
    raw_rows = fetch_all_markets(trade_date_str, av_key, indices)
    market_rows = build_market_rows(raw_rows)

    # Generate Claude narrative
    logger.info("Generating narrative with Claude Haiku...")
    try:
        claude_out = call_claude(raw_rows, anthropic_key)
        morning_brief = claude_out["morning_brief"]
        positioning_tips = claude_out["positioning_tips"]
    except Exception as e:
        logger.warning(f"Claude API failed: {e} — using static placeholder")
        morning_brief = (
            "*Markets closed the prior session. "
            "Full narrative unavailable — Claude API error.*"
        )
        positioning_tips = (
            "| Signal | Action | Rationale |\n"
            "|--------|--------|-------|\n"
            "| *Unavailable* | — | Claude API error |"
        )

    context = {
        "report_date": report_date,
        "trade_date": trade_date_str,
        "generated_at": generated_at,
        "run_at_flag": args.run_at,
        "market_rows": market_rows,
        "morning_brief": morning_brief,
        "positioning_tips": positioning_tips,
    }

    report = render_report(context)

    if args.preview:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(report)
    else:
        output_dir = BASE_DIR / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        date_slug = now_eastern.strftime("%Y-%m-%d")

        md_file = output_dir / f"daybreak_{date_slug}.md"
        md_file.write_text(report, encoding="utf-8")
        logger.info(f"Markdown saved: {md_file}")

        pdf_file = output_dir / f"daybreak_{date_slug}.pdf"
        logger.info("Generating PDF...")
        try:
            render_pdf(context, pdf_file)
            logger.info(f"PDF saved:      {pdf_file}")
        except Exception as e:
            logger.warning(f"PDF generation failed: {e} — markdown still saved")

        print(f"Markdown: {md_file}")
        print(f"PDF:      {pdf_file}")

        # Email delivery — fires only when SendGrid env vars are present
        sg_key = os.getenv("SENDGRID_API_KEY")
        email_from = os.getenv("EMAIL_FROM")
        email_to_raw = os.getenv("EMAIL_TO")
        if sg_key and email_from and email_to_raw:
            to_list = [e.strip() for e in email_to_raw.split(",") if e.strip()]
            logger.info(f"Sending email to: {', '.join(to_list)}")
            try:
                html_body = render_email_html(context)
                send_report(
                    sg_api_key=sg_key,
                    from_email=email_from,
                    to_emails=to_list,
                    report_date=context["report_date"],
                    html_body=html_body,
                    pdf_path=pdf_file,
                )
                print(f"Email:    sent to {', '.join(to_list)}")
            except Exception as e:
                logger.warning(f"Email failed: {e} — report still saved locally")
        else:
            logger.debug("Email skipped — SENDGRID_API_KEY / EMAIL_FROM / EMAIL_TO not set")


if __name__ == "__main__":
    main()
