import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import hunter

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

# Domains that are NOT real businesses — filter these out
BLOCKED_DOMAINS = {
    "en.wikipedia.org", "wikipedia.org", "reddit.com", "quora.com",
    "medium.com", "youtube.com", "facebook.com", "twitter.com",
    "linkedin.com", "instagram.com", "amazon.com", "yelp.com",
    "bbb.org", "glassdoor.com", "indeed.com", "crunchbase.com",
    "bloomberg.com", "forbes.com", "techcrunch.com", "news.ycombinator.com",
    "github.com", "stackoverflow.com", "x.com",
}

# Aggregator sites that list companies — skip these too
AGGREGATOR_DOMAINS = {
    "clutch.co", "g2.com", "goodfirms.co", "trustpilot.com",
    "capterra.com", "softwareadvice.com", "designrush.com",
    "topdevelopers.co", "toptal.com", "upwork.com", "fiverr.com",
    "sortlist.com", "themanifest.com", "bark.com",
    "techbehemoths.com", "itprofiles.com", "traffictail.com",
    "selectedfirms.co", "techreviewer.co", "extract.co",
    "appfutura.com", "topsoftwarecompanies.co", "wadline.com",
    "pangea.ai", "guru.com", "peopleperhour.com",
}

# Patterns that indicate a listicle/article title, NOT a real company page
LISTICLE_PATTERNS = [
    r"^\d+\s+(best|top|leading|largest|greatest)",    # "20 Best..."
    r"^(best|top)\s+\d+",                             # "Best 10..."
    r"^the\s+\d+\s+(best|top)",                       # "The 6 Best..."
    r"\d+\s+(best|top|leading).*\d{4}",               # "...10 best...2026"
    r"(best|top|leading|largest).*agencies.*\d{4}",    # "best agencies in 2026"
    r"(best|top|leading|largest).*companies.*\d{4}",   # "best companies in 2026"
    r"\d{4}\s*(guide|list|report|review|ranking)",     # "2026 guide/list/report"
    r"(guide|list|report|review|ranking).*\d{4}",     # "report 2026"
    r"^(top|best)\s+(digital|marketing|software|web)", # "Top digital marketing..."
    r"how to (find|choose|select|hire|pick)",          # "How to find..."
    r"(vs|versus|compared|comparison)",                # comparison articles
]


def _is_listicle_title(title: str) -> bool:
    """Returns True if the title looks like a listicle/article, not a company page."""
    lower = title.lower().strip()
    for pattern in LISTICLE_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False


def _extract_domain(url: str) -> str:
    """Extracts clean domain from a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _domain_to_company_name(domain: str) -> str:
    """Converts a domain like 'acme-solutions.com' to 'Acme Solutions'."""
    name = domain.split(".")[0]
    name = name.replace("-", " ").replace("_", " ")
    return name.title()


def scrape_website_info(url: str) -> dict:
    """
    Visits the actual company website using requests + BeautifulSoup.
    Extracts: company name, location, and page text for AI context.
    """
    result = {"name": "", "location": "", "text": ""}
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=6, allow_redirects=True)
        if resp.status_code != 200:
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        # ── Extract company name ──
        # Priority 1: og:site_name meta tag (most reliable)
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            result["name"] = og_site["content"].strip()

        # Priority 2: <title> tag, cleaned up
        if not result["name"]:
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                raw_title = title_tag.string.strip()
                parts = re.split(r"\s*[\-–—|:»]\s*", raw_title)
                generic = {"home", "official site", "official website", "welcome", ""}
                candidates = [p.strip() for p in parts if p.strip().lower() not in generic]
                if candidates:
                    result["name"] = min(candidates, key=len) if len(candidates) > 1 else candidates[0]

        # ── Extract location from structured data & meta tags ──
        import json as _json

        # Method 1: JSON-LD schema.org (most reliable — used by most business sites)
        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                ld_data = _json.loads(script_tag.string or "")
                # Handle both single objects and arrays
                items = ld_data if isinstance(ld_data, list) else [ld_data]
                for item in items:
                    addr = item.get("address") or item.get("location", {}).get("address", {})
                    if isinstance(addr, dict):
                        city = addr.get("addressLocality", "")
                        region = addr.get("addressRegion", "")
                        country = addr.get("addressCountry", "")
                        if isinstance(country, dict):
                            country = country.get("name", "")
                        parts = [p for p in [city, region, country] if p]
                        if parts:
                            result["location"] = ", ".join(parts)
                            break
                if result["location"]:
                    break
            except Exception:
                continue

        # Method 2: Geo meta tags
        if not result["location"]:
            geo_region = soup.find("meta", attrs={"name": "geo.region"})
            geo_place = soup.find("meta", attrs={"name": "geo.placename"})
            if geo_place and geo_place.get("content"):
                loc_parts = [geo_place["content"]]
                if geo_region and geo_region.get("content"):
                    loc_parts.append(geo_region["content"])
                result["location"] = ", ".join(loc_parts)

        # Method 3: Look for address patterns in page text
        if not result["location"]:
            full_html_text = soup.get_text(" ", strip=True)
            # Common US/international city + state/country patterns
            addr_patterns = [
                # "San Francisco, CA" or "New York, NY 10001"
                r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2}(?:\s+\d{5})?)",
                # "London, United Kingdom" or "Berlin, Germany"
                r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)",
            ]
            for pattern in addr_patterns:
                match = re.search(pattern, full_html_text)
                if match:
                    candidate = match.group(1).strip()
                    # Sanity check — should be reasonable length and not a sentence
                    if 4 < len(candidate) < 50:
                        result["location"] = candidate
                        break

        # ── Extract page text for AI context ──
        # Remove noise elements before text extraction
        for element in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
            element.decompose()

        text_blocks = []
        for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            clean_text = tag.get_text(strip=True)
            if clean_text and len(clean_text) > 15:
                text_blocks.append(clean_text)

        result["text"] = " ".join(text_blocks)[:1500]

    except Exception as e:
        print(f"  ⚠ Failed to scrape {url}: {e}")

    return result


def scrape_leads(industry: str, location: str, max_results: int = 10):
    """
    Scrapes real company leads from the web.

    Pipeline:
    1. DuckDuckGo search → find company URLs
    2. Filter out listicles, aggregators, and blocked sites
    3. Visit each real company site with requests + BeautifulSoup
    4. Extract real company name and page text from the HTML
    """
    all_blocked = BLOCKED_DOMAINS | AGGREGATOR_DOMAINS
    leads = []
    seen_domains = set()

    loc_str = location.strip() if location and location.strip() else ""
    loc_query = f" in {loc_str}" if loc_str else ""
    display_location = loc_str if loc_str else "Remote"

    # Queries designed to surface actual company homepages, not listicles
    queries = [
        f'"{industry}" company{loc_query} site',
        f"{industry} agency{loc_query}",
        f"{industry} services{loc_query} website",
        f"{industry} firm{loc_query} about us",
        f"{industry} provider{loc_query} contact",
    ]

    if DDGS:
        for query in queries:
            if len(leads) >= max_results:
                break
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=12))

                for res in results:
                    if len(leads) >= max_results:
                        break

                    title = res.get("title", "")
                    snippet = res.get("body", "")
                    url = res.get("href", "")

                    # Extract domain
                    domain = _extract_domain(url)

                    # Skip blocked, aggregators, already-seen
                    if not domain or domain in seen_domains:
                        continue
                    # Check if domain or any parent domain is blocked
                    if any(domain == bd or domain.endswith("." + bd) for bd in all_blocked):
                        continue

                    # ── KEY FIX: Skip listicle/article results ──
                    if _is_listicle_title(title):
                        print(f"  ⊘ Skipped listicle: \"{title}\"")
                        continue

                    seen_domains.add(domain)

                    # ── Visit actual website with requests + BeautifulSoup ──
                    site_info = scrape_website_info(url)

                    # Determine the best company name
                    # Priority: scraped site name > cleaned search title > domain name
                    company_name = ""

                    if site_info["name"] and len(site_info["name"]) <= 60:
                        company_name = site_info["name"]

                    if not company_name:
                        # Try extracting from search title
                        parts = re.split(r"\s*[\-–—|:»]\s*", title)
                        generic = {"home", "official site", "official website", "welcome", ""}
                        candidates = [p.strip() for p in parts if p.strip().lower() not in generic and len(p.strip()) >= 2]
                        if candidates:
                            company_name = min(candidates, key=len) if len(candidates) > 1 else candidates[0]

                    if not company_name or len(company_name) > 60 or len(company_name) < 2:
                        company_name = _domain_to_company_name(domain)

                    # Skip if company name still looks like a listicle (double check)
                    if _is_listicle_title(company_name):
                        print(f"  ⊘ Skipped (name still listicle): \"{company_name}\"")
                        continue

                    # Use deep-scraped website text if available, else search snippet
                    final_summary = site_info["text"] if site_info["text"] else snippet

                    # Use scraped location if found, else fall back to user's search query location
                    lead_location = site_info.get("location") or display_location

                    # Get verified email using Hunter.io (falls back to contact@domain if no key)
                    lead_email = hunter.find_best_email_for_domain(domain)

                    leads.append({
                        "company": company_name,
                        "industry": industry.strip(),
                        "location": lead_location,
                        "email": lead_email,
                        "summary_raw": final_summary,
                        "url": url,
                        "domain": domain,
                    })
                    print(f"  ✓ Found: {company_name} — {lead_location} — {lead_email}")

                # Small delay between queries to avoid rate limiting
                time.sleep(0.5)
            except Exception as e:
                print(f"Scraping error for query '{query}': {e}")
                continue

    # Fallback if DuckDuckGo returned nothing
    if not leads:
        print("DuckDuckGo returned no usable results — generating demo data.")
        ind = industry.strip().title()
        loc = loc_str if loc_str else "San Francisco, CA"
        demo_companies = [
            ("Apex", "Head of Operations", "Sarah Jenkins"),
            ("Pinnacle", "CEO", "Marcus Vance"),
            ("Summit", "CTO", "David Chen"),
            ("Vertex", "VP of Sales", "Rachel Kim"),
            ("Horizon", "Managing Director", "James O'Brien"),
        ]
        for prefix, role, name in demo_companies:
            slug = prefix.lower()
            leads.append({
                "company": f"{prefix} {ind}",
                "industry": industry.strip(),
                "location": loc,
                "email": f"{name.split()[0].lower()}@{slug}{industry.lower().replace(' ', '')}.com",
                "summary_raw": f"{prefix} {ind} is a leading company offering innovative solutions for the {industry} sector.",
                "url": f"https://{slug}{industry.lower().replace(' ', '')}.com",
                "domain": f"{slug}{industry.lower().replace(' ', '')}.com",
                "name_hint": name,
                "role_hint": role,
            })

    return leads[:max_results]
