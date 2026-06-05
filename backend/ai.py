import os
import json
import time
import requests
from google import genai
from dotenv import load_dotenv

load_dotenv()

gemini_api_key = os.getenv("GEMINI_API_KEY")
groq_api_key = os.getenv("GROQ_API_KEY")

# Gemini models to try in order
GEMINI_MODELS = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash-lite"]

# Groq models (fast open-source LLMs hosted by Groq)
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


def _call_gemini(prompt: str, max_retries: int = 2) -> str | None:
    """Calls Gemini with retry + model fallback."""
    if not gemini_api_key or gemini_api_key == "your_api_key_here":
        return None

    client = genai.Client(api_key=gemini_api_key)

    for model_name in GEMINI_MODELS:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return response.text.strip()
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "429" in err_str or "overloaded" in err_str.lower():
                    wait = (attempt + 1) * 2
                    print(f"  Gemini {model_name} rate-limited (attempt {attempt+1}). Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                else:
                    print(f"  Gemini {model_name} error: {e}")
                    break

        print(f"  Gemini {model_name} exhausted retries.")

    return None


def _call_groq(prompt: str, max_retries: int = 2) -> str | None:
    """Calls Groq API (OpenAI-compatible) as a fallback when Gemini is rate-limited."""
    if not groq_api_key:
        return None

    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json",
    }

    for model_name in GROQ_MODELS:
        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                        "max_tokens": 1024,
                    },
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                elif resp.status_code == 429:
                    wait = (attempt + 1) * 2
                    print(f"  Groq {model_name} rate-limited (attempt {attempt+1}). Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                else:
                    print(f"  Groq {model_name} HTTP {resp.status_code}: {resp.text[:200]}")
                    break
            except Exception as e:
                print(f"  Groq {model_name} error: {e}")
                break

        print(f"  Groq {model_name} exhausted retries.")

    return None


def _call_ai(prompt: str) -> str | None:
    """Tries Groq first, then falls back to Gemini if rate-limited."""
    # Try Groq first
    result = _call_groq(prompt)
    if result:
        print("  ✓ AI response from Groq")
        return result

    # Fallback to Gemini
    print("  → Groq unavailable, falling back to Gemini...")
    result = _call_gemini(prompt)
    if result:
        print("  ✓ AI response from Gemini")
        return result

    print("  ✗ All AI providers failed")
    return None


def _parse_json_response(raw: str) -> dict | None:
    """Strips markdown fences and parses JSON from AI response."""
    text = raw
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    # Also handle ```json prefix
    if text.startswith("json"):
        text = text[4:]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}\n  Raw: {text[:300]}")
        return None


def enrich_lead(lead_data: dict) -> dict:
    """
    Step 1: Enriches a lead with name, role, and company summary.
    Does NOT generate the outreach email draft.
    """
    company = lead_data.get("company", "Unknown Company")
    industry = lead_data.get("industry", "Unknown")
    location = lead_data.get("location", "Unknown")
    snippet = lead_data.get("summary_raw", "")
    domain = lead_data.get("domain", "")

    name_hint = lead_data.get("name_hint", "")
    role_hint = lead_data.get("role_hint", "")

    prompt = f"""You are an expert B2B sales intelligence assistant. I scraped a business from the web. Generate realistic enrichment data for my CRM.

SCRAPED DATA:
- Company: {company}
- Industry: {industry}
- Location: {location}
- Website snippet: {snippet[:800]}
- Domain: {domain}

GENERATE the following as valid JSON (no markdown, no code fences):
{{
  "contact_name": "A realistic full name of a likely decision-maker at this company (e.g. CEO, VP Sales, Head of Growth). Make it sound real and human.",
  "contact_role": "Their likely job title (e.g. CEO, CTO, VP of Sales, Head of Marketing)",
  "summary": "A professional 2-sentence company summary based on the snippet. If the snippet is vague, infer from the company name and industry."
}}

Return ONLY the JSON object. No explanation, no markdown."""

    raw = _call_ai(prompt)

    if raw:
        result = _parse_json_response(raw)
        if result:
            return {
                "name": result.get("contact_name", name_hint or "Decision Maker"),
                "role": result.get("contact_role", role_hint or "Executive"),
                "summary": result.get("summary", snippet),
            }

    # Fallback — all AI providers failed
    return {
        "name": name_hint or "Decision Maker",
        "role": role_hint or "Executive",
        "summary": snippet if snippet else f"{company} is a company operating in the {industry} space.",
    }


def draft_outreach_email(lead_data: dict) -> str:
    """
    Step 2: Generates a personalized cold outreach email for an already-enriched lead.
    """
    name = lead_data.get("name", "there")
    role = lead_data.get("role", "Executive")
    company = lead_data.get("company", "Unknown Company")
    industry = lead_data.get("industry", "Unknown")
    location = lead_data.get("location", "Unknown")
    summary = lead_data.get("summary", "")

    first_name = name.split()[0] if name and name != "Decision Maker" else "there"

    prompt = f"""You are an expert cold email copywriter for B2B sales outreach.

Write a personalized 3-4 sentence cold outreach email for the following lead:

LEAD INFO:
- Contact: {name} ({role})
- Company: {company}
- Industry: {industry}
- Location: {location}
- About: {summary[:500]}

INSTRUCTIONS:
- Address the contact by their first name ({first_name})
- Reference their company and what they do specifically
- Pitch our AI-powered lead generation and outreach automation platform
- Keep it concise, professional, and warm
- Sign off as [Your Name]

Return ONLY the email text. No subject line, no JSON, no markdown."""

    raw = _call_ai(prompt)

    if raw:
        text = raw.strip().strip('"').strip("'")
        return text

    # Fallback
    return f"Hi {first_name},\n\nI came across {company} while researching {industry} companies in {location}. Your work in this space caught my attention.\n\nI'd love to show you how our AI-powered platform can automate your lead generation and outreach pipeline.\n\nWould you be open to a quick 15-minute chat this week?\n\nBest,\n[Your Name]"


