# Framework Foundry — Daybreak Edition

A Python CLI tool that auto-generates a daily pre-market report for US traders, delivered as both Markdown and a styled PDF.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## What It Does

Runs each morning before market open and produces a two-output report covering:

1. **The Morning Brief** — AI-written narrative summary of yesterday's action
2. **Global Markets** — US, Europe, and Asia index closes with colored % changes
3. **Asia Overnight** — Live prices at generation time *(coming soon)*
4. **US Pre-Market** — SPY/QQQ before the bell *(coming soon)*
5. **Key Events Last 24h** — Economic releases with market implications *(coming soon)*
6. **Day Ahead** — Calendar + earnings *(coming soon)*
7. **Positioning Tips** — AI-generated signal → action table with real ETF tickers

**Outputs:**
- `output/daybreak_YYYY-MM-DD.md` — plain Markdown
- `output/daybreak_YYYY-MM-DD.pdf` — styled PDF matching the Framework Foundry newsletter design

## Sample Output

The PDF is styled to match the Framework Foundry Weekly newsletter:
- Dark navy header band with teal accent stripe
- Section headings with teal underline
- Market table with green/red colored change values
- Clean Helvetica serif layout on US letter paper

## Setup

### 1. Clone & install dependencies

```bash
git clone https://github.com/githubuser20152014/market-daybreak.git
cd market-daybreak
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```
ALPHAVANTAGE_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

| Key | Where to get it | Free tier |
|-----|----------------|-----------|
| `ALPHAVANTAGE_API_KEY` | [alphavantage.co](https://www.alphavantage.co/support/#api-key) | 25 req/day |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) | Pay-per-use |

### 3. Run

```bash
# Generate today's report (saves .md + .pdf to output/)
python generate_daybreak.py

# Preview in terminal without saving
python generate_daybreak.py --preview

# Simulate a specific generation time
python generate_daybreak.py --run-at 07:00
```

## Project Structure

```
market-daybreak/
├── generate_daybreak.py        # Main CLI entrypoint
├── data/
│   └── fetch_global_markets.py # Alpha Vantage EOD fetcher with file cache
├── templates/
│   ├── daybreak_template.jinja2 # Markdown report template
│   └── daybreak_pdf.html        # Styled PDF template
├── config/
│   └── indices.json             # Index symbols and groupings
├── output/                      # Generated reports (gitignored)
├── .env.example                 # API key template
└── requirements.txt
```

## Data Sources

| Source | Usage |
|--------|-------|
| [Alpha Vantage](https://www.alphavantage.co/) `TIME_SERIES_DAILY` | EOD prices for US/EU/Asia ETF proxies |
| [Anthropic Claude](https://www.anthropic.com/) `claude-haiku-4-5` | Morning brief narrative + positioning tips |

**Index proxies** (ETFs used instead of caret symbols for free-tier compatibility):

| Index | Symbol |
|-------|--------|
| S&P 500 | SPY |
| Dow Jones | DIA |
| Nasdaq | QQQ |
| DAX (Europe) | EWG |
| Nikkei (Asia) | EWJ |

## Notes

- **Caching**: API responses are cached to `data/cache/` by symbol + date. Re-runs on the same day skip all Alpha Vantage calls and complete in ~5 seconds.
- **Rate limiting**: 15-second sleep between live API calls to stay within Alpha Vantage's free tier (25 req/day).
- **Holiday awareness**: Correctly skips US market holidays and weekends when determining the prior trading day.

## Roadmap

- [ ] Live Asia overnight prices
- [ ] SPY/QQQ pre-market quotes
- [ ] Finnhub economic calendar integration
- [ ] GitHub Actions cron for 7 AM EST delivery
- [ ] Email delivery via smtplib
