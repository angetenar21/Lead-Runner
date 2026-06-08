import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

# ── BLOCKED DOMAINS ──
# Social media, encyclopedias, forums, job boards, investor sites
BLOCKED_DOMAINS = {
    # Social & community
    "en.wikipedia.org", "wikipedia.org", "reddit.com", "quora.com",
    "medium.com", "youtube.com", "facebook.com", "twitter.com",
    "linkedin.com", "instagram.com", "x.com", "threads.net",
    "tiktok.com", "pinterest.com", "tumblr.com",
    # E-commerce & reviews
    "amazon.com", "yelp.com", "bbb.org",
    # Jobs & careers
    "glassdoor.com", "indeed.com", "ziprecruiter.com", "monster.com",
    "lever.co", "greenhouse.io", "angel.co", "wellfound.com",
    # Developer / code
    "github.com", "gitlab.com", "stackoverflow.com", "stackexchange.com",
    "npmjs.com", "pypi.org",
    # Investor / startup databases
    "crunchbase.com", "pitchbook.com", "owler.com", "zoominfo.com",
    "dnb.com", "hoovers.com",
}

# ── NEWS & MEDIA DOMAINS ──
# These write articles ABOUT industries but are NOT businesses in those industries
NEWS_MEDIA_DOMAINS = {
    # Major tech/business news
    "forbes.com", "bloomberg.com", "techcrunch.com", "reuters.com",
    "nytimes.com", "wsj.com", "bbc.com", "bbc.co.uk", "cnn.com",
    "theguardian.com", "washingtonpost.com", "usatoday.com",
    "businessinsider.com", "insider.com", "cnbc.com", "ft.com",
    "economist.com", "fortune.com", "inc.com", "fastcompany.com",
    "entrepreneur.com", "hbr.org",
    # Tech media
    "wired.com", "theverge.com", "arstechnica.com", "zdnet.com",
    "cnet.com", "engadget.com", "gizmodo.com", "techradar.com",
    "pcmag.com", "computerworld.com", "informationweek.com",
    "venturebeat.com", "thenextweb.com", "mashable.com",
    "9to5mac.com", "appleinsider.com", "tomsguide.com",
    "tomshardware.com", "howtogeek.com", "lifehacker.com",
    "macrumors.com", "androidcentral.com", "xda-developers.com",
    "bleepingcomputer.com", "hackaday.com", "slashdot.org",
    "theregister.com", "computing.co.uk",
    # Industry news / analysis
    "businesscloud.co.uk", "channelfutures.com", "channele2e.com",
    "csoonline.com", "darkreading.com", "securityweek.com",
    "threatpost.com", "infosecurity-magazine.com", "scmagazine.com",
    "cybersecuritynews.com", "helpnetsecurity.com",
    # General media / broadcast
    "aol.com", "news.ycombinator.com", "msn.com", "yahoo.com",
    "huffpost.com", "vox.com", "slate.com", "salon.com",
    "thedailybeast.com", "politico.com", "axios.com",
    "rnz.co.nz", "abc.net.au", "cbc.ca", "dw.com",
    "aljazeera.com", "euronews.com", "france24.com",
    # Research / analyst
    "gartner.com", "forrester.com", "idc.com", "statista.com",
    "mckinsey.com", "deloitte.com", "pwc.com", "ey.com",
    "kpmg.com", "accenture.com", "bain.com", "bcg.com",
    # Content farms / SEO blogs
    "hubspot.com", "neilpatel.com", "searchenginejournal.com",
    "searchengineland.com", "moz.com", "semrush.com",
    "backlinko.com", "ahrefs.com", "contentmarketinginstitute.com",
    "socialmediaexaminer.com", "sproutsocial.com", "buffer.com",
    # Event/conference/award sites
    "eventbrite.com", "meetup.com",
    # B2B databases and lead lists
    "aventionmedia.com", "builtwith.com", "similarweb.com",
}

# ── AGGREGATOR DOMAINS ──
# Sites that list/rank/review companies
AGGREGATOR_DOMAINS = {
    "clutch.co", "g2.com", "goodfirms.co", "trustpilot.com",
    "capterra.com", "softwareadvice.com", "designrush.com",
    "topdevelopers.co", "toptal.com", "upwork.com", "fiverr.com",
    "sortlist.com", "themanifest.com", "bark.com",
    "techbehemoths.com", "itprofiles.com", "traffictail.com",
    "selectedfirms.co", "techreviewer.co", "extract.co",
    "appfutura.com", "topsoftwarecompanies.co", "wadline.com",
    "pangea.ai", "guru.com", "peopleperhour.com",
    "upcity.com", "behance.net", "dribbble.com",
    "awwwards.com", "cssnectar.com", "themeforest.net", "envato.com",
    "sitebuilderreport.com", "framer.com",
}

# ── LISTICLE TITLE PATTERNS ──
LISTICLE_PATTERNS = [
    r"^\d+\s+(best|top|leading|largest|greatest)",
    r"^(best|top)\s+\d+",
    r"^the\s+\d+\s+(best|top)",
    r"\d+\s+(best|top|leading).*\d{4}",
    r"(best|top|leading|largest).*agencies.*\d{4}",
    r"(best|top|leading|largest).*companies.*\d{4}",
    r"\d{4}\s*(guide|list|report|review|ranking)",
    r"(guide|list|report|review|ranking).*\d{4}",
    r"^(top|best)\s+(digital|marketing|software|web)",
    r"how to (find|choose|select|hire|pick)",
    r"(vs|versus|compared|comparison)",
]

# ── ARTICLE TITLE PATTERNS ──
# Titles that look like news articles / blog posts, NOT company names
ARTICLE_PATTERNS = [
    r"^how\s+(a|an|the|to)\b",             # "How a Cybersecurity Firm..."
    r"^why\s+(a|an|the|you|we|it)\b",      # "Why You Need..."
    r"^what\s+(is|are|you|we|it)\b",       # "What is..."
    r"^when\s+(a|an|the|to)\b",            # "When to..."
    r"^where\s+(a|an|the|to)\b",           # "Where to..."
    r"^\d+\s+(ways|tips|tricks|steps|reasons|things|signs|trends|facts|examples)",
    r"\b(entered|launches|announces|acquires|raises|partners|expands|reports|warns|reveals|says|told|according)\b",
    r"\b(new market|market share|industry report|case study|white paper|webinar)\b",
    r"\b(interview|podcast|recap|roundup|opinion|editorial|analysis)\b",
    r":\s*(a|an|the|how|why|what)\s+",     # Subtitle pattern
]


def _is_listicle_title(title: str) -> bool:
    """Returns True if the title looks like a listicle or directory."""
    t = title.strip().lower()

    if any(kw in t for kw in ["list of", "directory", "examples", "roundup", "ranking"]):
        return True

    if re.search(r"^\s*(top|best|\d+\+?)\s", t):
        return True

    if re.search(r"\b(\d+\+?\s+)?(best|top|greatest|largest)\b", t):
        return True

    for pattern in LISTICLE_PATTERNS:
        if re.search(pattern, t):
            return True

    return False


def _is_article_title(title: str) -> bool:
    """Returns True if the title looks like a news article or blog post."""
    t = title.strip().lower()

    # Very long titles (>80 chars) are almost always articles
    if len(t) > 80:
        return True

    for pattern in ARTICLE_PATTERNS:
        if re.search(pattern, t):
            return True

    # If it has 10+ words, it's probably a headline not a company name
    if len(t.split()) > 10:
        return True

    return False


def _is_news_media_domain(domain: str) -> bool:
    """Returns True if the domain is a news, media, or content site."""
    d = domain.lower()
    for nd in NEWS_MEDIA_DOMAINS:
        if d == nd or d.endswith("." + nd):
            return True
    return False


def _is_directory_domain(domain: str) -> bool:
    """Returns True if the domain is a known directory or aggregator."""
    d = domain.lower()
    for bd in AGGREGATOR_DOMAINS:
        if bd in d:
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


def _validate_company_name(name: str) -> bool:
    """Returns True if the name looks like a real company name."""
    if not name or len(name) < 2 or len(name) > 60:
        return False
    if _is_listicle_title(name):
        return False
    if _is_article_title(name):
        return False
    return True


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
                candidates = [p.strip() for p in parts if p.strip().lower() not in generic and len(p.strip()) >= 2]
                if candidates:
                    result["name"] = min(candidates, key=len) if len(candidates) > 1 else candidates[0]

        # ── Extract location from structured data & meta tags ──
        import json as _json

        # Method 1: JSON-LD schema.org
        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                ld_data = _json.loads(script_tag.string or "")
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
            addr_patterns = [
                r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2}(?:\s+\d{5})?)",
                r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)",
            ]
            for pattern in addr_patterns:
                match = re.search(pattern, full_html_text)
                if match:
                    candidate = match.group(1).strip()
                    if 4 < len(candidate) < 50:
                        result["location"] = candidate
                        break

        # ── Extract page text for AI context ──
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
    2. Filter out listicles, aggregators, news/media sites, and blocked sites
    3. Visit each real company site with requests + BeautifulSoup
    4. Extract real company name and page text from the HTML
    5. Validate that company name is real (not an article title)
    """
    all_blocked = BLOCKED_DOMAINS | NEWS_MEDIA_DOMAINS | AGGREGATOR_DOMAINS
    leads = []
    seen_domains = set()

    loc_str = location.strip() if location and location.strip() else ""
    loc_query = f" in {loc_str}" if loc_str else ""
    display_location = loc_str if loc_str else "Remote"

    # Search queries engineered to find actual company homepages
    ind = industry.strip()
    queries = [
        f'"{ind}" "our services" OR "about us" OR "our team"{loc_query}',
        f'"{ind}" company "contact us"{loc_query}',
        f'{ind} firm "our clients" OR "case studies"{loc_query}',
        f'{ind} agency OR provider official website{loc_query}',
        f'{ind} solutions OR consulting{loc_query} -best -top -list -review -news -article',
    ]

    # Fetch extra results to compensate for filtering
    fetch_per_query = max(max_results, 15)

    if DDGS:
        for query in queries:
            if len(leads) >= max_results:
                break
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=fetch_per_query))

                for res in results:
                    if len(leads) >= max_results:
                        break

                    title = res.get("title", "")
                    snippet = res.get("body", "")
                    url = res.get("href", "")

                    # Extract domain
                    domain = _extract_domain(url)

                    # ── FILTER LAYER 1: Domain-based filtering ──
                    if not domain or domain in seen_domains:
                        continue

                    if any(domain == bd or domain.endswith("." + bd) for bd in all_blocked):
                        print(f"  ⊘ Blocked domain: {domain}")
                        continue

                    if _is_news_media_domain(domain):
                        print(f"  ⊘ Skipped news/media: {domain}")
                        continue

                    if _is_directory_domain(domain):
                        print(f"  ⊘ Skipped directory: {domain}")
                        continue

                    # ── FILTER LAYER 2: Title-based filtering ──
                    if _is_listicle_title(title):
                        print(f"  ⊘ Skipped listicle: \"{title}\"")
                        continue

                    if _is_article_title(title):
                        print(f"  ⊘ Skipped article: \"{title}\"")
                        continue

                    seen_domains.add(domain)

                    # ── Visit actual website with requests + BeautifulSoup ──
                    site_info = scrape_website_info(url)

                    # ── FILTER LAYER 3: Post-scrape validation ──
                    scraped_name = (site_info.get("name") or "").strip()
                    if scraped_name and _is_article_title(scraped_name):
                        print(f"  ⊘ Scraped name is article-like: \"{scraped_name}\"")
                        continue

                    # Determine the best company name
                    company_name = ""

                    if scraped_name and _validate_company_name(scraped_name):
                        company_name = scraped_name

                    if not company_name:
                        parts = re.split(r"\s*[\-–—|:»]\s*", title)
                        generic = {"home", "official site", "official website", "welcome", ""}
                        candidates = [p.strip() for p in parts if p.strip().lower() not in generic and len(p.strip()) >= 2]
                        candidates = [c for c in candidates if _validate_company_name(c)]
                        if candidates:
                            company_name = min(candidates, key=len)

                    if not company_name or not _validate_company_name(company_name):
                        company_name = _domain_to_company_name(domain)

                    if not _validate_company_name(company_name):
                        print(f"  ⊘ Invalid company name: \"{company_name}\"")
                        continue

                    # Use deep-scraped website text if available, else search snippet
                    final_summary = site_info["text"] if site_info["text"] else snippet

                    # Use scraped location if found, else fall back to user's search query location
                    lead_location = site_info.get("location") or display_location

                    # --- Email Fallback ---
                    # Use a generic fallback since we're no longer using ZeroBounce
                    lead_email = site_info.get("emails", [f"info@{domain}"])[0] if site_info.get("emails") else f"info@{domain}"
                    lead_name = ""
                    lead_role = ""

                    leads.append({
                        "company": company_name,
                        "industry": industry.strip(),
                        "location": lead_location,
                        "email": lead_email,
                        "name_hint": lead_name,
                        "role_hint": lead_role,
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
        ind_title = industry.strip().title()
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
                "company": f"{prefix} {ind_title}",
                "industry": industry.strip(),
                "location": loc,
                "email": f"{name.split()[0].lower()}@{slug}{industry.lower().replace(' ', '')}.com",
                "summary_raw": f"{prefix} {ind_title} is a leading company offering innovative solutions for the {industry} sector.",
                "url": f"https://{slug}{industry.lower().replace(' ', '')}.com",
                "domain": f"{slug}{industry.lower().replace(' ', '')}.com",
                "name_hint": name,
                "role_hint": role,
            })

    return leads[:max_results]
