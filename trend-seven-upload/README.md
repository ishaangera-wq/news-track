# Trending Sources Dashboard

Playwright-based scraper for collecting trending stories from:

- Indian Express
- Hindustan Times
- LiveMint
- India Today
- Times of India ETimes
- Times of India Viral News
- NDTV

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Usage

```bash
python scrape_trending_sources.py --site all --headless --out_csv web/trending_sources.csv --out_json web/trending_sources.json --out_html web/index.html
```

## Output

Each row contains:

- `source`
- `rank`
- `headline`
- `link`
- `collected_at_iso`

## Hosting

The `web/index.html` file is self-contained and can be hosted as a static page on GitHub Pages, Netlify, or Vercel.
