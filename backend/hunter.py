import os
import requests
from dotenv import load_dotenv

load_dotenv()

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")

def find_best_email_for_domain(domain: str) -> str:
    """
    Uses Hunter.io Domain Search API to find the best real email for a domain.
    If no key is provided or the API fails, it falls back to contact@domain.
    """
    fallback_email = f"contact@{domain}"

    if not HUNTER_API_KEY:
        print(f"  [Hunter.io] Skipping verification for {domain} (No HUNTER_API_KEY in .env)")
        return fallback_email

    try:
        url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={HUNTER_API_KEY}"
        resp = requests.get(url, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            emails = data.get("data", {}).get("emails", [])
            if emails:
                # Try to find a decision maker, otherwise return the first one found
                for e in emails:
                    if e.get("type") == "personal":
                        print(f"  [Hunter.io] ✓ Found real personal email: {e.get('value')} for {domain}")
                        return e.get("value")
                
                print(f"  [Hunter.io] ✓ Found real generic email: {emails[0].get('value')} for {domain}")
                return emails[0].get("value")
            else:
                print(f"  [Hunter.io] ✗ No emails found for {domain}")
                return fallback_email
        elif resp.status_code == 401:
            print(f"  [Hunter.io] ⚠ Invalid API key")
            return fallback_email
        else:
            print(f"  [Hunter.io] API error {resp.status_code}: {resp.text}")
            return fallback_email

    except Exception as e:
        print(f"  [Hunter.io] Exception: {e}")
        return fallback_email
