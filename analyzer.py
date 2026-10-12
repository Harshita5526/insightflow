
import os, re, json
import requests
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass

TOPICS = [
 ("Fraud & Scams", r"\b(?:scam|fraud|fake|unauthori|cheat|stolen|phish)"),
 ("Damaged Packaging", r"\b(?:packag|damaged)"),
 ("Wrong / Missing Items", r"\b(?:wrong|missing|incorrect)"),
 ("Website & Checkout Bugs", r"\b(?:website|checkout|payment|glitch|purchase|login|app\b)"),
 ("Delivery Delays", r"\b(?:deliver|delay|late|shipping|arriv)"),
 ("Customer Support", r"\b(?:support|service|agent|representative|staff|response)"),
 ("Product Quality", r"\b(?:quality|stopped working|broke|defect|durab|perform)"),
 ("Features & Value", r"\b(?:feature|value|price|worth|innovative)"),
]
SEV = {"Fraud & Scams": 5, "Damaged Packaging": 4, "Wrong / Missing Items": 4, "Website & Checkout Bugs": 4,
       "Delivery Delays": 3, "Customer Support": 3, "Product Quality": 4, "Features & Value": 2}
NEG = re.compile(r"\b(?:damaged|missing|wrong|scam|fraud|glitch|delay|late|not as advertised|stopped working|broke|rude|unhelpful|poor|terrible|worst|disappoint|unresponsive|incorrect|difficult|fake|unfortunately|did not|didn't|never|slow|problem|cheat)")
POS = re.compile(r"\b(?:great|excellent|helpful|friendly|satisfied|innovative|worth|love|good|amazing|perfect|fast|quick|knowledgeable|easy|smooth|professional|recommend|impressed|well)")
NAMES = [t[0] for t in TOPICS] + ["General Feedback"]


def rule(review, cat=""):
    t = str(review).lower()
    topic = next((n for n, p in TOPICS if re.search(p, t)), "General Feedback")
    s = len(POS.findall(t)) - len(NEG.findall(t))
    if cat == "Fraud and Scam" and s == 0:
        s = -1
    sent = "positive" if s > 0 else "negative" if s < 0 else "neutral"
    sev = SEV.get(topic, 2) if sent == "negative" else (2 if sent == "neutral" else 1)
    return {"sentiment": sent, "topic": topic, "severity": sev, "engine": "Rules"}


def _prompt(batch):
    lines = "\n".join(f"{i}. {r}" for i, r in enumerate(batch))
    return ("Classify each customer review. Return ONLY a JSON array of objects "
            '{"i":int,"sentiment":"positive|neutral|negative","topic":one of ' + json.dumps(NAMES) +
            ',"severity":1-5 (5 = most serious)}.\n\nReviews:\n' + lines)


def _claude(p):
    r = requests.post("https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": "claude-sonnet-4-6", "max_tokens": 4000, "messages": [{"role": "user", "content": p}]}, timeout=90)
    return r.json()["content"][0]["text"]


def _gemini(p, js=True):
    m = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
        params={"key": os.environ["GEMINI_API_KEY"]}, timeout=90,
        json={"contents": [{"parts": [{"text": p}]}], "generationConfig": ({"responseMimeType": "application/json"} if js else {})})
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def engine():
    return "Claude" if os.getenv("ANTHROPIC_API_KEY") else "Gemini" if os.getenv("GEMINI_API_KEY") else "Rules"


def analyze_many(reviews, cats=None):
    """LLM (Claude or Gemini, if a key is set) with rule-based fallback per batch."""
    cats = cats or {}
    out = {r: rule(r, cats.get(r, "")) for r in reviews}
    eng = engine(); fn = {"Claude": _claude, "Gemini": _gemini}.get(eng)
    if fn:
        for i in range(0, len(reviews), 25):
            b = reviews[i:i + 25]
            try:
                txt = fn(_prompt(b))
                for x in json.loads(re.search(r"\[.*\]", txt, re.S).group()):
                    if x["sentiment"] in ("positive", "neutral", "negative") and x["topic"] in NAMES:
                        out[b[x["i"]]] = {"sentiment": x["sentiment"], "topic": x["topic"],
                                          "severity": max(1, min(5, int(x["severity"]))), "engine": eng}
            except Exception as e:
                print("LLM batch failed, using rules:", str(e)[:150])
    return out


def llm_text(prompt):
    """Free-text answer from Claude/Gemini, or None when no key / failure."""
    e = engine()
    try:
        return (_claude(prompt) if e == "Claude" else _gemini(prompt, False) if e == "Gemini" else "").strip() or None
    except Exception as ex:
        print("LLM answer failed:", str(ex)[:150]); return None
