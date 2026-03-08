Upload the contents of this folder to your GitHub repository using the GitHub web interface.

After upload, do this one rename step in GitHub:

1. Create a folder path `.github/workflows/`
2. Move or recreate `github-workflows/refresh-dashboard.yml` as `.github/workflows/refresh-dashboard.yml`

Important folders/files in this upload package:

- `scrape_india_news_trending.py`
- `requirements.txt`
- `README.md`
- `web/index.html`
- `web/dashboard.html`
- `web/india_trending.csv`
- `web/india_trending.json`
- `github-workflows/refresh-dashboard.yml`

For Vercel or Netlify, set the publish directory to `web`.
