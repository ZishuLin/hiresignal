"""
Job Fetcher
Fetches job description text from a URL.
Supports: LinkedIn, Indeed, Glassdoor, Workday, Greenhouse, Lever, and generic pages.
Supports JS-rendered pages via Selenium (headless Chrome).
Falls back through: Selenium → Direct → Google Cache → SerpAPI snippet.
"""

import os
import re
import sys
import requests
from typing import Optional, Tuple
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# Playwright for JS-rendered pages
PLAYWRIGHT_AVAILABLE = False
SELENIUM_AVAILABLE = False  # kept for backward compat
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

# Sites that require JS rendering
JS_REQUIRED_SITES = [
    "shopify.com",
    "linkedin.com",
    "workday.com",
    "myworkdayjobs.com",
    "taleo.net",
    "successfactors.com",
    "icims.com",
    "smartrecruiters.com",
    "jobvite.com",
]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

# CSS selectors for known job sites
SITE_SELECTORS = {
    "linkedin.com": [
        ".description__text",
        ".jobs-description__content",
        ".jobs-box__html-content",
        "[class*='description']",
    ],
    "indeed.com": [
        "#jobDescriptionText",
        ".jobsearch-jobDescriptionText",
        "[data-testid='jobsearch-JobComponent-description']",
    ],
    "glassdoor.com": [
        ".desc",
        "[class*='jobDescription']",
        ".jobDescriptionContent",
    ],
    "greenhouse.io": [
        "#content",
        ".job-post",
        "[class*='job-description']",
    ],
    "lever.co": [
        ".section-wrapper",
        ".posting-description",
        "[class*='content']",
    ],
    "workday.com": [
        "[data-automation-id='jobPostingDescription']",
        ".job-requisition-details",
    ],
}

# Generic fallback selectors
GENERIC_SELECTORS = [
    "article",
    "main",
    "[class*='job-description']",
    "[class*='jobDescription']",
    "[class*='job_description']",
    "[id*='job-description']",
    "[id*='jobDescription']",
    "[class*='posting']",
    "[class*='description']",
    "section",
]


def _is_url(text: str) -> bool:
    """Check if a string is a URL."""
    try:
        result = urlparse(text.strip())
        return result.scheme in ("http", "https") and bool(result.netloc)
    except Exception:
        return False


def _get_domain(url: str) -> str:
    """Extract root domain from URL."""
    try:
        netloc = urlparse(url).netloc.lower()
        # Remove www.
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def _extract_text_bs4(html: str, url: str) -> Optional[str]:
    """Extract job description text using BeautifulSoup."""
    if not BS4_AVAILABLE:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Remove noise elements
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "iframe", "noscript", "button"]):
        tag.decompose()

    domain = _get_domain(url)

    # Try site-specific selectors first
    for site_domain, selectors in SITE_SELECTORS.items():
        if site_domain in domain:
            for selector in selectors:
                try:
                    el = soup.select_one(selector)
                    if el:
                        text = el.get_text(separator=" ", strip=True)
                        if len(text) > 200:
                            return _clean_text(text)
                except Exception:
                    continue

    # Try generic selectors
    for selector in GENERIC_SELECTORS:
        try:
            elements = soup.select(selector)
            for el in elements:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 300:
                    return _clean_text(text)
        except Exception:
            continue

    # Last resort: all paragraph text
    paras = soup.find_all("p")
    text = " ".join(p.get_text(strip=True) for p in paras if len(p.get_text(strip=True)) > 30)
    if len(text) > 200:
        return _clean_text(text)

    # Absolute fallback: full body text
    body = soup.find("body")
    if body:
        text = body.get_text(separator=" ", strip=True)
        return _clean_text(text[:5000])

    return None


def _clean_text(text: str) -> str:
    """Clean extracted text: remove excessive whitespace and boilerplate."""
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove common boilerplate patterns
    text = re.sub(r'(cookie|privacy policy|terms of service|all rights reserved).*', '',
                  text, flags=re.IGNORECASE)
    return text[:6000]  # cap at 6000 chars


def _extract_text_regex(html: str) -> Optional[str]:
    """Fallback: extract text using regex without BS4."""
    # Remove scripts and styles
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Extract paragraph text
    paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    text = " ".join(re.sub(r'<[^>]+>', '', p).strip() for p in paras)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:5000] if len(text) > 100 else None



def _fetch_with_playwright(url: str) -> Tuple[Optional[str], str]:
    """
    Use Playwright (headless Edge/Chromium) to fetch JS-rendered job pages.
    Handles LinkedIn, Shopify Careers, Workday, and other JS-heavy sites.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return None, "playwright_not_installed"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel="msedge",
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            page = context.new_page()

            # Block images/fonts to speed up load
            page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf}", lambda r: r.abort())

            # Navigate
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
            except PlaywrightTimeout:
                pass  # Proceed with whatever loaded

            # Site-specific waits
            domain = _get_domain(url)
            try:
                if "linkedin.com" in domain:
                    page.wait_for_selector(".description__text", timeout=8000)
                elif "shopify.com" in domain:
                    page.wait_for_selector("main", timeout=8000)
                    page.wait_for_timeout(2000)
                elif "workday" in domain:
                    page.wait_for_selector("[data-automation-id='jobPostingDescription']", timeout=8000)
                elif "greenhouse.io" in domain:
                    page.wait_for_selector("#content", timeout=8000)
                elif "lever.co" in domain:
                    page.wait_for_selector(".posting-description", timeout=8000)
                else:
                    page.wait_for_timeout(3000)
            except Exception:
                page.wait_for_timeout(2000)

            html = page.content()
            browser.close()

        if BS4_AVAILABLE:
            text = _extract_text_bs4(html, url)
        else:
            text = _extract_text_regex(html)

        if text and len(text) > 200:
            return text, "playwright_edge"
        return None, "playwright_empty"

    except Exception as e:
        return None, f"playwright_error_{type(e).__name__}"


def _needs_playwright(url: str) -> bool:
    """Check if a URL likely needs Playwright for JS rendering."""
    domain = _get_domain(url)
    return any(js_site in domain for js_site in JS_REQUIRED_SITES)


# Keep for backward compat
def _fetch_with_selenium(url: str) -> Tuple[Optional[str], str]:
    return _fetch_with_playwright(url)


def _needs_selenium(url: str) -> bool:
    return _needs_playwright(url)


def _fetch_direct(url: str) -> Tuple[Optional[str], str]:
    """
    Attempt direct HTTP fetch of the job page.
    Returns (extracted_text, method_used).
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text

        if BS4_AVAILABLE:
            text = _extract_text_bs4(html, url)
        else:
            text = _extract_text_regex(html)

        if text and len(text) > 150:
            return text, "direct_fetch"

        return None, "direct_fetch_empty"
    except requests.exceptions.HTTPError as e:
        return None, f"http_error_{e.response.status_code}"
    except Exception as e:
        return None, f"error_{type(e).__name__}"


def _fetch_via_google_cache(url: str) -> Tuple[Optional[str], str]:
    """
    Try fetching via Google Cache as fallback for blocked sites.
    """
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
    try:
        resp = requests.get(cache_url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            html = resp.text
            if BS4_AVAILABLE:
                text = _extract_text_bs4(html, url)
            else:
                text = _extract_text_regex(html)
            if text and len(text) > 150:
                return text, "google_cache"
    except Exception:
        pass
    return None, "cache_failed"


def _fetch_via_serpapi(url: str) -> Tuple[Optional[str], str]:
    """
    Use SerpAPI to get a cached/indexed version of the page.
    """
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        return None, "no_serpapi_key"
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": url, "api_key": key, "num": 3, "engine": "google"},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("organic_results", [])
        for r in results:
            snippet = r.get("snippet", "")
            if len(snippet) > 100:
                return snippet, "serpapi_snippet"
    except Exception:
        pass
    return None, "serpapi_failed"


def _extract_company_from_url(url: str) -> Optional[str]:
    """Try to extract company name from the job URL."""
    domain = _get_domain(url)

    # LinkedIn: linkedin.com/jobs/view/TITLE-at-COMPANY-ID
    m = re.search(r'linkedin\.com/jobs/(?:view|search)/([^/?]+)', url)
    if m:
        slug = m.group(1)
        # "senior-engineer-at-shopify-123456" -> "shopify"
        at_match = re.search(r'-at-([a-z0-9-]+)-\d+', slug)
        if at_match:
            return at_match.group(1).replace("-", " ").title()

    # Indeed: indeed.com/viewjob + company in page (can't get without fetch)
    # Greenhouse: boards.greenhouse.io/COMPANY/jobs/ID
    m = re.search(r'greenhouse\.io/([^/]+)/jobs', url)
    if m:
        return m.group(1).replace("-", " ").title()

    # Lever: jobs.lever.co/COMPANY/ID
    m = re.search(r'lever\.co/([^/]+)/', url)
    if m:
        return m.group(1).replace("-", " ").title()

    # Workday: COMPANY.wd5.myworkdayjobs.com
    m = re.match(r'([a-z0-9-]+)\.(?:wd\d+\.)?myworkdayjobs\.com', domain)
    if m:
        return m.group(1).replace("-", " ").title()

    # Generic: use domain root as company name
    parts = domain.split(".")
    if parts[0] not in ("jobs", "careers", "boards", "www"):
        return parts[0].title()

    return None


def fetch_job_posting(url: str) -> dict:
    """
    Main function: fetch a job posting from a URL.
    Tries multiple strategies and returns extracted text + metadata.

    Returns:
        {
            "success": bool,
            "text": str,           # extracted JD text
            "company": str,        # guessed company name
            "method": str,         # how it was fetched
            "url": str,
            "error": str,          # if failed
            "char_count": int,
        }
    """
    url = url.strip()
    domain = _get_domain(url)
    company_guess = _extract_company_from_url(url)

    # Strategy 1: Playwright for JS-rendered sites (LinkedIn, Shopify, Workday etc.)
    if _needs_playwright(url) and PLAYWRIGHT_AVAILABLE:
        text, method = _fetch_with_playwright(url)
    else:
        text, method = _fetch_direct(url)

    # Strategy 2: Playwright fallback if direct fetch got too little content
    if (not text or len(text) < 300) and PLAYWRIGHT_AVAILABLE and not _needs_playwright(url):
        pw_text, pw_method = _fetch_with_playwright(url)
        if pw_text and len(pw_text) > (len(text) if text else 0):
            text, method = pw_text, pw_method

    # Strategy 3: Google Cache
    if not text or len(text) < 200:
        cache_text, cache_method = _fetch_via_google_cache(url)
        if cache_text and len(cache_text) > (len(text) if text else 0):
            text, method = cache_text, cache_method

    # Strategy 4: SerpAPI snippet (last resort)
    if not text or len(text) < 150:
        serp_text, serp_method = _fetch_via_serpapi(url)
        if serp_text:
            text, method = serp_text, serp_method

    if text:
        return {
            "success": True,
            "text": text,
            "company": company_guess or domain,
            "method": method,
            "url": url,
            "error": None,
            "char_count": len(text),
        }
    else:
        return {
            "success": False,
            "text": "",
            "company": company_guess or domain,
            "method": method,
            "url": url,
            "error": f"Could not fetch job posting from {domain}. Site may require login.",
            "char_count": 0,
        }
