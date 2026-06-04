import os
import json
import time
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

# Models to try in order — if primary is overloaded (503), fall back
MODELS = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash-lite"]


def _call_gemini(prompt: str, max_retries: int = 3) -> str | None:
    """
    Calls the Gemini API with automatic retry + model fallback.
    Returns the response text or None on failure.
    """
    if not api_key or api_key == "your_api_key_here":
        return None

    client = genai.Client(api_key=api_key)

    for model_name in MODELS:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return response.text.strip()
            except Exception as e:
                err_str = str(e)
                # 503 = overloaded, 429 = rate limit → retry with backoff
                if "503" in err_str or "429" in err_str or "overloaded" in err_str.lower():
                    wait = (attempt + 1) * 2  # 2s, 4s, 6s
                    print(f"Gemini {model_name} attempt {attempt+1} got rate-limited. Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                else:
                    print(f"Gemini {model_name} error: {e}")
                    break  # Non-retryable error, try next model

        print(f"Model {model_name} exhausted retries, trying next model...")

    return None


def enrich_lead(lead_data: dict) -> dict:
    """
    Takes raw lead data, sends it to Gemini, and returns
    an enriched dict with: name, role, summary, email_draft.
    """
    company = lead_data.get("company", "Unknown Company")
    industry = lead_data.get("industry", "Unknown")
    location = lead_data.get("location", "Unknown")
    snippet = lead_data.get("summary_raw", "")
    domain = lead_data.get("domain", "")

    # If scraper already provided name/role hints (fallback mode), use them
    name_hint = lead_data.get("name_hint", "")
    role_hint = lead_data.get("role_hint", "")

    prompt = f"""You are an expert B2B sales intelligence assistant. I scraped a business from the web. Generate realistic enrichment data for my CRM.

SCRAPED DATA:
- Company: {company}
- Industry: {industry}
- Location: {location}
- Website snippet: {snippet}
- Domain: {domain}

GENERATE the following as valid JSON (no markdown, no code fences):
{{
  "contact_name": "A realistic full name of a likely decision-maker at this company (e.g. CEO, VP Sales, Head of Growth). Make it sound real and human.",
  "contact_role": "Their likely job title (e.g. CEO, CTO, VP of Sales, Head of Marketing)",
  "summary": "A professional 2-sentence company summary based on the snippet. If the snippet is vague, infer from the company name and industry.",
  "email_draft": "A personalized 3-4 sentence cold outreach email. Address the contact by first name. Reference their company and what they do. Pitch our AI-powered lead generation platform. Sign off as [Your Name]."
}}

Return ONLY the JSON object. No explanation, no markdown."""

    raw = _call_gemini(prompt)

    if raw:
        try:
            # Strip markdown fences if present
            text = raw
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            result = json.loads(text)
            return {
                "name": result.get("contact_name", name_hint or "Decision Maker"),
                "role": result.get("contact_role", role_hint or "Executive"),
                "summary": result.get("summary", snippet),
                "email_draft": result.get("email_draft", ""),
            }
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}\nRaw response: {raw[:300]}")

    # Fallback — no API or all retries failed
    first_name = name_hint.split()[0] if name_hint else "there"
    return {
        "name": name_hint or "Decision Maker",
        "role": role_hint or "Executive",
        "summary": snippet if snippet else f"{company} is a company operating in the {industry} space.",
        "email_draft": f"Hi {first_name},\n\nI came across {company} while researching {industry} companies in {location}. Your work in this space caught my attention.\n\nI'd love to show you how our AI-powered platform can automate your lead generation and outreach pipeline.\n\nWould you be open to a quick 15-minute chat this week?\n\nBest,\n[Your Name]",
    }
