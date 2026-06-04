import time
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
    "bloomberg.com", "forbes.com", "techcrunch.com",
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


def scrape_leads(industry: str, location: str, max_results: int = 10):
    """
    Scrapes real company leads from the web using DuckDuckGo search.
    Uses multiple search queries for variety and diversity.
    Returns up to max_results leads.
    """
    all_blocked = BLOCKED_DOMAINS | AGGREGATOR_DOMAINS
    leads = []
    seen_domains = set()

    # Multiple search queries for more diverse results
    loc_str = f" in {location}" if location and location.strip() else ""
    queries = [
        f"best {industry} companies{loc_str}",
        f"top {industry} firms{loc_str}",
        f"{industry} agency{loc_str} website",
        f"{industry} services company{loc_str}",
        f"leading {industry} providers{loc_str}",
    ]

    if DDGS:
        for query in queries:
            if len(leads) >= max_results:
                break
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=10))

                for res in results:
                    if len(leads) >= max_results:
                        break

                    title = res.get("title", "")
                    snippet = res.get("body", "")
                    url = res.get("href", "")

                    # Extract domain
                    domain = url.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]

                    # Skip blocked sites or already-seen domains
                    if not domain or domain in all_blocked or domain in seen_domains:
                        continue

                    seen_domains.add(domain)

                    # Extract company name from search title
                    company_name = title.split("-")[0].split("|")[0].split("–")[0].split("—")[0].split(":")[0].strip()

                    # Clean up: remove common suffixes like "Home", "Official Site", etc.
                    for suffix in ["Home", "Official Site", "Official Website", "Welcome"]:
                        company_name = company_name.replace(suffix, "").strip()

                    # If name is too long, too short, or empty, use the domain
                    if not company_name or len(company_name) > 50 or len(company_name) < 2:
                        company_name = domain.split(".")[0].replace("-", " ").title()

                    leads.append({
                        "company": company_name,
                        "industry": industry.strip(),
                        "location": location.strip() if location else "Remote",
                        "email": f"contact@{domain}",
                        "summary_raw": snippet,
                        "url": url,
                        "domain": domain,
                    })

                # Small delay between queries to avoid rate limiting
                time.sleep(0.5)
            except Exception as e:
                print(f"Scraping error for query '{query}': {e}")
                continue

    # Fallback if DuckDuckGo returned nothing
    if not leads:
        print("DuckDuckGo returned no usable results — generating demo data.")
        ind = industry.strip().title()
        loc = location.strip() if location and location.strip() else "San Francisco, CA"
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
