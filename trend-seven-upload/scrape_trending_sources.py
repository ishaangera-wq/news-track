from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlparse, urlunparse
import argparse
import csv
import html
import json
import re
import ssl
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

UA_DESKTOP_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

SITE_JOBS = [
    {
        "site_key": "indianexpress",
        "source": "Indian Express",
        "url": "https://indianexpress.com/section/trending/",
        "base_url": "https://indianexpress.com/",
        "selectors": ["h2 a", "h3 a", "article a", "main a"],
        "allow_patterns": [],
        "exclude_patterns": [
            r"/section/trending/?$",
            r"/photos/",
            r"/videos/",
            r"/web-stories/",
            r"/explained/",
        ],
    },
    {
        "site_key": "hindustantimes",
        "source": "Hindustan Times",
        "mode": "rss",
        "url": "https://www.hindustantimes.com/feeds/rss/trending/rssfeed.xml",
        "base_url": "https://www.hindustantimes.com/",
        "selectors": [],
        "allow_patterns": [],
        "exclude_patterns": [
            r"/trending/?$",
            r"/photos/",
            r"/videos/",
            r"/web-stories/",
        ],
    },
    {
        "site_key": "livemint",
        "source": "LiveMint",
        "url": "https://www.livemint.com/us/trending",
        "base_url": "https://www.livemint.com/",
        "selectors": ["h2 a", "h3 a", "article a", "main a", "li a"],
        "allow_patterns": [],
        "exclude_patterns": [
            r"/us/trending/?$",
            r"/photos/",
            r"/videos/",
            r"/mint-lounge/",
        ],
    },
    {
        "site_key": "indiatoday",
        "source": "India Today",
        "url": "https://www.indiatoday.in/trending-news",
        "base_url": "https://www.indiatoday.in/",
        "selectors": ["h2 a", "h3 a", "article a", "main a"],
        "allow_patterns": [],
        "exclude_patterns": [
            r"/trending-news/?$",
            r"/video/",
            r"/livetv",
            r"/topic/",
            r"/newsletter",
            r"/photo/",
        ],
    },
    {
        "site_key": "toi_etimes",
        "source": "TOI ETimes",
        "url": "https://timesofindia.indiatimes.com/etimes/trending",
        "base_url": "https://timesofindia.indiatimes.com/",
        "selectors": [],
        "allow_patterns": [r"/articleshow/\d+\.cms"],
        "exclude_patterns": [r"/etimes/trending/?$", r"/photostory/", r"/videoshow/"],
    },
    {
        "site_key": "toi_viral",
        "source": "TOI Viral News",
        "url": "https://timesofindia.indiatimes.com/viral-news",
        "base_url": "https://timesofindia.indiatimes.com/",
        "selectors": [],
        "allow_patterns": [r"/articleshow/\d+\.cms"],
        "exclude_patterns": [r"/viral-news/?$", r"/photostory/", r"/videoshow/"],
    },
    {
        "site_key": "ndtv",
        "source": "NDTV",
        "url": "https://www.ndtv.com/trends",
        "base_url": "https://www.ndtv.com/",
        "selectors": [],
        "allow_patterns": [],
        "exclude_patterns": [
            r"/trends/?$",
            r"/video/",
            r"/photos/",
            r"/live-updates/",
            r"/topic/",
            r"/indian-railway/pnr-status",
            r"/TermsAndConditions\.aspx",
            r"/codeofethics\.aspx",
        ],
        "prefer_channel": "chrome",
    },
]

BLOCK_TITLE_PATTERNS = [
    r"^\s*$",
    r"^advertisement$",
    r"^sponsored$",
    r"^recommended stories$",
    r"^follow us on",
    r"^read epaper$",
    r"^subscribe",
    r"^newsletter$",
    r"^privacy policy$",
    r"^terms and conditions$",
    r"^live updates",
    r"^latest news$",
    r"^news$",
]


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def add_stealth(ctx_or_page):
    if hasattr(ctx_or_page, "add_init_script"):
        ctx_or_page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => false});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            const gp = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {
              if (p === 37445) return 'Intel Inc.';
              if (p === 37446) return 'ANGLE (Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)';
              return gp.call(this, p);
            };
            """
        )


def click_cookie_banners(page):
    selectors = [
        "button:has-text('Accept')",
        "button:has-text('I Agree')",
        "button:has-text('AGREE')",
        "button:has-text('Got it')",
        "button:has-text('Continue')",
        "button[aria-label='Accept']",
        "[data-testid='accept']",
        "#onetrust-accept-btn-handler",
        "#wzrk-confirm",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible():
                locator.click(timeout=1200)
                time.sleep(0.2)
                break
        except Exception:
            pass


def clean_headline(text):
    title = re.sub(r"\s+", " ", text or "").strip()
    title = re.sub(r"<[^>]+>", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def canonicalize_url(link, job):
    parsed = urlparse(link)
    clean_path = re.sub(r"/+", "/", parsed.path or "/")
    canonical = parsed._replace(query="", fragment="", path=clean_path)
    canonical_url = urlunparse(canonical)

    if job["site_key"] in {"toi_etimes", "toi_viral"}:
        match = re.search(r"/articleshow/(\d+)\.cms", clean_path, re.I)
        if match:
            article_id = match.group(1)
            return f"{job['base_url'].rstrip('/')}/articleshow/{article_id}.cms"

    return canonical_url


def dedupe_key(job, link):
    if job["site_key"] in {"toi_etimes", "toi_viral"}:
        match = re.search(r"/articleshow/(\d+)\.cms", link, re.I)
        if match:
            return f"{job['site_key']}:{match.group(1)}"
    return link


def fetch_rss_items(job):
    request = urllib.request.Request(
        job["url"],
        headers={
            "User-Agent": UA_DESKTOP_CHROME,
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        },
    )
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
        payload = response.read()

    root = ET.fromstring(payload)
    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        if title and link:
            items.append({"title": title, "href": link})
    return items


def extract_anchors(page, selectors=None):
    return page.evaluate(
        """
        ({ selectors }) => {
          const out = [];
          const seen = new Set();
          const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
          const allAnchors = selectors && selectors.length
            ? selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)))
            : Array.from(document.querySelectorAll('a[href]'));

          allAnchors.forEach((a) => {
            const href = a.href || a.getAttribute('href') || '';
            let title = norm(a.getAttribute('title') || a.getAttribute('aria-label') || '');
            if (!title) {
              const img = a.querySelector('img[alt]');
              if (img) title = norm(img.getAttribute('alt') || '');
            }
            if (!title) {
              title = norm(a.textContent || '');
            }
            if (!href || !title) return;
            const key = href + '|' + title;
            if (seen.has(key)) return;
            seen.add(key);
            out.push({ href, title });
          });

          return out;
        }
        """,
        {"selectors": selectors or []},
    )


def is_valid_candidate(link, title, job):
    lower_title = title.lower()
    parsed = urlparse(link)
    path = parsed.path.rstrip("/")

    if parsed.scheme not in ("http", "https"):
        return False
    if any(re.search(pattern, link, re.I) for pattern in job["exclude_patterns"]):
        return False
    if job["allow_patterns"] and not any(re.search(pattern, link, re.I) for pattern in job["allow_patterns"]):
        return False
    if any(re.search(pattern, lower_title, re.I) for pattern in BLOCK_TITLE_PATTERNS):
        return False
    if len(title) < 12 or len(title.split()) < 3:
        return False
    if "taboola" in link.lower():
        return False
    if parsed.netloc and urlparse(job["base_url"]).netloc not in parsed.netloc:
        return False
    if path in ("", "/"):
        return False
    if len([part for part in path.split("/") if part]) < 1:
        return False
    return True


def normalize_rows(job, candidates):
    rows = []
    seen_links = set()
    for item in candidates:
        raw_link = urljoin(job["base_url"], item["href"])
        link = canonicalize_url(raw_link, job)
        title = clean_headline(item["title"])
        key = dedupe_key(job, link)
        if key in seen_links:
            continue
        if not is_valid_candidate(link, title, job):
            continue
        seen_links.add(key)
        rows.append(
            {
                "source": job["source"],
                "rank": len(rows) + 1,
                "headline": title,
                "link": link,
            }
        )
    return rows


def render_html(rows):
    data_json = json.dumps(rows, ensure_ascii=False)
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Trending Sources Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root {{ --font: system-ui, -apple-system, Segoe UI, Roboto, Arial; }}
  body {{ font-family: var(--font); margin: 24px; }}
  header {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
  input, select, button {{ font: 14px var(--font); padding: 8px 10px; border-radius: 10px; border:1px solid #ddd; }}
  .grid {{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 18px; }}
  .panel {{ border:1px solid #eee; border-radius: 14px; padding: 16px; box-shadow: 0 1px 6px rgba(0,0,0,0.05); }}
  .panel h2 {{ font-size: 18px; margin: 0 0 10px; }}
  ol {{ margin:0; padding-left: 22px; }}
  li {{ margin: 8px 0; line-height: 1.35; }}
  a {{ text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .muted {{ color:#666; font-size: 12px; }}
  .meta {{ display:flex; gap:8px; align-items:center; margin-top: 6px; }}
  @media (max-width: 1100px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
<header>
  <strong>Trending Sources Dashboard</strong>
  <span class="muted">Self-contained dashboard with embedded scraper output.</span>
  <input id="search" placeholder="Search headline...">
  <select id="sort">
    <option value="rankAsc">Sort by rank (asc)</option>
    <option value="rankDesc">Sort by rank (desc)</option>
    <option value="alpha">Sort by headline (A→Z)</option>
  </select>
  <button id="reload">Reset filters</button>
</header>
<div class="grid" id="grid"></div>
<script>
const RAW = {data_json};
const SOURCES = [...new Set(RAW.map(d => d.source))];
const state = {{ raw: RAW, filterText: "", sortMode: "rankAsc" }};

function asc(a, b) {{
  return a < b ? -1 : a > b ? 1 : 0;
}}

function applyFilters(rows) {{
  let result = rows.slice();
  if (state.filterText) {{
    const q = state.filterText.toLowerCase();
    result = result.filter(d => (d.headline || "").toLowerCase().includes(q));
  }}
  switch (state.sortMode) {{
    case "rankAsc": result.sort((a, b) => a.rank - b.rank); break;
    case "rankDesc": result.sort((a, b) => b.rank - a.rank); break;
    case "alpha": result.sort((a, b) => asc(a.headline, b.headline)); break;
  }}
  return result;
}}

function panelId(source) {{
  return source.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}}

function ensurePanels() {{
  const grid = document.querySelector("#grid");
  grid.innerHTML = "";
  for (const source of SOURCES) {{
    const panel = document.createElement("div");
    const id = panelId(source);
    panel.className = "panel";
    panel.innerHTML = `<h2>${{source}}</h2><div class="meta" id="${{id}}-meta"></div><ol id="${{id}}-list"></ol>`;
    grid.appendChild(panel);
  }}
}}

function renderList(listId, rows) {{
  const list = document.querySelector(listId);
  list.innerHTML = "";
  for (const row of rows) {{
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.href = row.link;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = `#${{row.rank}} ${{row.headline}}`;
    li.appendChild(link);
    list.appendChild(li);
  }}
}}

function renderMeta(metaId, rows) {{
  const el = document.querySelector(metaId);
  if (!rows.length) {{
    el.textContent = "No data";
    return;
  }}
  el.textContent = `Items: ${{rows.length}} · Collected: ${{rows[0].collected_at_iso || ""}}`;
}}

function render() {{
  for (const source of SOURCES) {{
    const rows = applyFilters(state.raw.filter(d => d.source === source));
    const id = panelId(source);
    renderList(`#${{id}}-list`, rows);
    renderMeta(`#${{id}}-meta`, rows);
  }}
}}

document.querySelector("#search").addEventListener("input", ev => {{
  state.filterText = ev.target.value || "";
  render();
}});
document.querySelector("#sort").addEventListener("change", ev => {{
  state.sortMode = ev.target.value;
  render();
}});
document.querySelector("#reload").addEventListener("click", () => {{
  state.filterText = "";
  state.sortMode = "rankAsc";
  document.querySelector("#search").value = "";
  document.querySelector("#sort").value = "rankAsc";
  render();
}});

ensurePanels();
render();
</script>
"""


def scrape_job(page, job, wait_ms, retries, nav_timeout_ms):
    if job.get("mode") == "rss":
        try:
            return normalize_rows(job, fetch_rss_items(job))
        except Exception as exc:
            print(f"[WARN] {job['source']} RSS extraction failed: {exc}", file=sys.stderr)
            return []

    items = []
    last_error = None
    for _ in range(retries + 1):
        try:
            page.goto(job["url"], wait_until="domcontentloaded", timeout=nav_timeout_ms)
            time.sleep(wait_ms / 1000.0)
            click_cookie_banners(page)
            for _ in range(3):
                page.mouse.wheel(0, 1400)
                time.sleep(0.5)
            candidates = extract_anchors(page, selectors=job.get("selectors"))
            items = normalize_rows(job, candidates)
            if items:
                return items
        except Exception as exc:
            last_error = exc
    if last_error:
        print(f"[WARN] {job['source']} extraction failed: {last_error}", file=sys.stderr)
    return items


def launch_browser_and_page(playwright, args, channel_override=None):
    browser_type = {
        "chromium": playwright.chromium,
        "firefox": playwright.firefox,
        "webkit": playwright.webkit,
    }[args.engine]
    launch_kwargs = {
        "headless": args.headless,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    channel = channel_override
    if args.engine == "chromium" and channel is None and args.channel in ("chrome", "msedge"):
        channel = args.channel
    if args.engine == "chromium" and channel:
        launch_kwargs["channel"] = channel
    browser = browser_type.launch(**launch_kwargs)
    context = browser.new_context(
        viewport={"width": 1440, "height": 960},
        user_agent=UA_DESKTOP_CHROME,
        locale="en-US",
        timezone_id="Asia/Kolkata",
    )
    add_stealth(context)
    page = context.new_page()
    add_stealth(page)
    return browser, context, page


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--site",
        choices=["indianexpress", "hindustantimes", "livemint", "indiatoday", "toi_etimes", "toi_viral", "ndtv", "all"],
        default="all",
    )
    parser.add_argument("--out_csv", default="trending_sources.csv")
    parser.add_argument("--out_json", default="trending_sources.json")
    parser.add_argument("--out_html", default="")
    parser.add_argument("--engine", choices=["chromium", "firefox", "webkit"], default="chromium")
    parser.add_argument("--channel", choices=["none", "chrome", "msedge"], default="none")
    parser.add_argument("--wait_ms", type=int, default=2500)
    parser.add_argument("--nav_timeout_ms", type=int, default=60000)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser, context, page = launch_browser_and_page(playwright, args)
        chrome_browser = chrome_context = chrome_page = None
        if args.engine == "chromium" and args.channel == "none":
            try:
                chrome_browser, chrome_context, chrome_page = launch_browser_and_page(
                    playwright,
                    args,
                    channel_override="chrome",
                )
            except Exception as exc:
                print(f"[WARN] Chrome fallback unavailable: {exc}", file=sys.stderr)

        timestamp = now_iso()
        collected = []
        for job in SITE_JOBS:
            if args.site not in (job["site_key"], "all"):
                continue
            active_page = chrome_page if job.get("prefer_channel") == "chrome" and chrome_page is not None else page
            items = scrape_job(
                active_page,
                job=job,
                wait_ms=args.wait_ms,
                retries=args.retries,
                nav_timeout_ms=args.nav_timeout_ms,
            )
            for row in items:
                row["collected_at_iso"] = timestamp
            collected.extend(items)

        for index, row in enumerate(collected, 1):
            print(f"{index:02d}. [{row['source']}] #{row['rank']} {row['headline']} | {row['link']}")

        if args.out_csv:
            with open(args.out_csv, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["source", "rank", "headline", "link", "collected_at_iso"],
                )
                writer.writeheader()
                writer.writerows(collected)
            print(f"Saved CSV: {args.out_csv} ({len(collected)} rows)")

        if args.out_json:
            with open(args.out_json, "w", encoding="utf-8") as handle:
                json.dump(collected, handle, ensure_ascii=False, indent=2)
            print(f"Saved JSON: {args.out_json} ({len(collected)} items)")

        if args.out_html:
            with open(args.out_html, "w", encoding="utf-8") as handle:
                handle.write(render_html(collected))
            print(f"Saved HTML: {args.out_html}")

        context.close()
        browser.close()
        if chrome_context is not None:
            chrome_context.close()
        if chrome_browser is not None:
            chrome_browser.close()


if __name__ == "__main__":
    main()
