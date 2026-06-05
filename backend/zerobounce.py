import os
import requests
from dotenv import load_dotenv

load_dotenv()

ZEROBOUNCE_API_KEY = os.getenv("ZEROBOUNCE_API_KEY")

def verify_email(email: str) -> bool:
    """
    Verifies an email using ZeroBounce.
    Returns True if valid or catch-all, False if invalid or bouncing.
    If the API key is missing or an error occurs, we assume True (benefit of the doubt).
    """
    if not email or "@" not in email:
        return False

    if not ZEROBOUNCE_API_KEY:
        print(f"  [ZeroBounce] Skipping verification for {email} (No ZEROBOUNCE_API_KEY in .env)")
        return True

    try:
        url = f"https://api.zerobounce.net/v2/validate?api_key={ZEROBOUNCE_API_KEY}&email={email}"
        resp = requests.get(url, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            
            # Check if there is an error
            if "error" in data:
                print(f"  [ZeroBounce] ⚠ API Error: {data['error']}")
                return True # Fail open to not block lead gen
                
            status = data.get("status")
            
            # "valid" and "catch-all" are generally safe to send to
            if status in ["valid", "catch-all"]:
                print(f"  [ZeroBounce] ✓ {email} is {status}")
                return True
            else:
                print(f"  [ZeroBounce] ✗ {email} is {status} (rejected)")
                return False
        else:
            print(f"  [ZeroBounce] API error {resp.status_code}: {resp.text[:100]}")
            return True

    except Exception as e:
        print(f"  [ZeroBounce] Exception: {e}")
        return True

def guess_and_verify_email(first_name: str, last_name: str, domain: str) -> str:
    """
    If Apollo didn't return an email, we guess standard patterns and run them
    through ZeroBounce until one is valid.
    """
    if not first_name:
        return f"contact@{domain}"
        
    f = first_name.lower().strip()
    l = last_name.lower().strip() if last_name else ""
    
    patterns = [
        f"{f}@{domain}",
        f"{f}.{l}@{domain}" if l else None,
        f"{f[0]}{l}@{domain}" if l else None,
        f"contact@{domain}",
        f"info@{domain}"
    ]
    
    for email in filter(None, patterns):
        if verify_email(email):
            return email
            
    # If all fail, return the first guess
    return f"{f}@{domain}"
