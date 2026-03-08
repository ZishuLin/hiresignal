"""
layoffs.fyi Scraper
Fetches and caches historical layoff data from layoffs.fyi.
Data is stored locally in data/layoffs_history.csv to minimize requests.
"""

import os
import re
import csv
import time
import requests
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_FILE = DATA_DIR / "layoffs_history.csv"
CACHE_TTL_HOURS = 24  # re-fetch if cache older than this

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _serpapi_search(query: str, num: int = 8) -> List[Dict]:
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        return []
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": key, "num": num, "engine": "google"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("organic_results", [])
    except Exception as e:
        print(f"[layoffs_fyi] SerpAPI error: {e}")
        return []


def _cache_is_fresh() -> bool:
    """Return True if the cache file exists and was written recently."""
    if not CACHE_FILE.exists():
        return False
    mtime = datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)
    return datetime.now() - mtime < timedelta(hours=CACHE_TTL_HOURS)


def _read_cache() -> List[Dict]:
    """Read cached layoff records from CSV."""
    records = []
    if not CACHE_FILE.exists():
        return records
    try:
        with open(CACHE_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
    except Exception as e:
        print(f"[layoffs_fyi] Cache read error: {e}")
    return records


def _write_cache(records: List[Dict]):
    """Write layoff records to CSV cache."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not records:
        return
    fields = list(records[0].keys())
    try:
        with open(CACHE_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
    except Exception as e:
        print(f"[layoffs_fyi] Cache write error: {e}")


def _fetch_from_web() -> List[Dict]:
    """
    Attempt to fetch layoff data from layoffs.fyi via direct request + SerpAPI fallback.
    Returns list of standardized layoff records.
    """
    records = []

    # Strategy 1: Direct request to layoffs.fyi
    try:
        resp = requests.get("https://layoffs.fyi", headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            html = resp.text
            # Parse table rows: each row has company, date, employees laid off, industry, source
            # layoffs.fyi renders a table; extract rows with regex (JS-rendered data may not be available)
            rows = re.findall(
                r'<tr[^>]*>.*?</tr>', html, re.DOTALL | re.IGNORECASE
            )
            for row in rows[:200]:
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
                cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                if len(cells) >= 4:
                    company = cells[0]
                    date_str = cells[1] if len(cells) > 1 else ""
                    num_str = cells[2] if len(cells) > 2 else ""
                    industry = cells[3] if len(cells) > 3 else ""

                    # Clean numbers
                    num_clean = re.sub(r'[^\d]', '', num_str)
                    try:
                        num = int(num_clean) if num_clean else 0
                    except ValueError:
                        num = 0

                    if company and len(company) > 1:
                        records.append({
                            "company": company,
                            "date": date_str,
                            "num_laid_off": num,
                            "industry": industry,
                            "source": "layoffs.fyi_direct",
                        })
    except Exception as e:
        print(f"[layoffs_fyi] Direct fetch error: {e}")

    # Strategy 2: SerpAPI search for recent layoff news to supplement
    if len(records) < 10:
        results = _serpapi_search("site:layoffs.fyi layoffs 2024 2025", num=10)
        for r in results:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            text = title + " " + snippet

            # Extract company name (usually first word(s) before "Layoffs" or "laid off")
            company_m = re.match(r'^([A-Za-z0-9\s\-\.]+?)\s+(?:Layoffs?|laid off|cuts?)', title, re.IGNORECASE)
            company = company_m.group(1).strip() if company_m else ""

            # Extract number
            num_m = re.search(r'([\d,]+)\s+(?:employees?|workers?|people|jobs?)', text, re.IGNORECASE)
            num = 0
            if num_m:
                try:
                    num = int(num_m.group(1).replace(",", ""))
                except ValueError:
                    pass

            # Extract year
            year_m = re.search(r'(202\d)', text)
            date_str = year_m.group(1) if year_m else "unknown"

            if company:
                records.append({
                    "company": company,
                    "date": date_str,
                    "num_laid_off": num,
                    "industry": "",
                    "source": "layoffs.fyi_serpapi",
                })

    return records


def get_all_layoffs(force_refresh: bool = False) -> List[Dict]:
    """
    Return all layoff records, using cache if available and fresh.
    Set force_refresh=True to bypass cache.
    """
    if not force_refresh and _cache_is_fresh():
        records = _read_cache()
        if records:
            return records

    records = _fetch_from_web()
    if records:
        _write_cache(records)
    return records


def search_company(company: str, force_refresh: bool = False) -> Dict:
    """
    Search layoff history for a specific company.
    Returns structured data including events, total headcount, and recency.
    """
    all_records = get_all_layoffs(force_refresh=force_refresh)

    # Filter by company name (fuzzy match)
    company_lower = company.lower()
    matched = []
    for r in all_records:
        rec_company = r.get("company", "").lower()
        if company_lower in rec_company or rec_company in company_lower:
            matched.append(r)

    # If no cache hits, do a targeted SerpAPI search
    if not matched:
        results = _serpapi_search(f"layoffs.fyi {company} layoffs employees", num=6)
        for r in results:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            text = title + " " + snippet

            if company.lower() not in text.lower():
                continue

            num_m = re.search(r'([\d,]+)\s+(?:employees?|workers?|people|jobs?)', text, re.IGNORECASE)
            num = 0
            if num_m:
                try:
                    num = int(num_m.group(1).replace(",", ""))
                except ValueError:
                    pass

            year_m = re.search(r'(202\d)', text)
            date_str = year_m.group(1) if year_m else "unknown"

            if num > 0 or company.lower() in title.lower():
                matched.append({
                    "company": company,
                    "date": date_str,
                    "num_laid_off": num,
                    "industry": "",
                    "source": "targeted_search",
                    "title": title[:80],
                    "snippet": snippet[:120],
                })

    # Calculate summary stats
    total_laid_off = sum(
        int(r.get("num_laid_off", 0) or 0) for r in matched
    )
    years = sorted(set(
        r.get("date", "")[:4] for r in matched if r.get("date", "")[:4].isdigit()
    ))
    most_recent = years[-1] if years else None

    # Determine recency risk
    if most_recent and int(most_recent) >= 2024:
        recency = "very_recent"
    elif most_recent and int(most_recent) >= 2022:
        recency = "recent"
    elif most_recent:
        recency = "historical"
    else:
        recency = "none"

    return {
        "company": company,
        "has_layoff_history": len(matched) > 0,
        "event_count": len(matched),
        "total_laid_off_estimate": total_laid_off,
        "most_recent_year": most_recent,
        "recency": recency,
        "events": matched[:6],  # top 6 events
    }


def get_industry_layoffs(industry: str) -> List[Dict]:
    """
    Get layoff data for an industry sector (e.g., 'tech', 'fintech', 'healthcare').
    Useful for contextualizing a single company's risk.
    """
    all_records = get_all_layoffs()
    industry_lower = industry.lower()
    matched = [
        r for r in all_records
        if industry_lower in r.get("industry", "").lower()
    ]
    return matched[:20]
