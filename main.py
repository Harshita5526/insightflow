import json, io, os, re, time, tempfile, datetime as dt
from collections import Counter
from fastapi import FastAPI, UploadFile, File, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
from analyzer import analyze_many, llm_text  # also loads .env

BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, "data.json"), encoding="utf-8"))
ROWS, META = D["rows"], D["meta"]
TODAY = dt.date.today()
IF = os.path.join(tempfile.gettempdir(), "issues.json")
try: ISSUES = json.load(open(IF))
except Exception: ISSUES = []
app = FastAPI(title="InsightFlow")

ACTIONS = {
 "Website & Checkout Bugs": "Assign engineering to audit checkout and payment errors; add error monitoring and a status banner.",
 "Fraud & Scams": "Escalate to trust and safety: verify flagged sellers, tighten listing checks and publish a buyer-protection policy.",
 "Wrong / Missing Items": "Add a pick-and-pack verification step and auto-offer refunds or replacements.",
 "Damaged Packaging": "Review packaging standards with logistics partners and track damage rate per carrier.",
 "Delivery Delays": "Send proactive delay notices and renegotiate SLAs with slow carriers.",
 "Customer Support": "Cut first-response time with macros, and coach agents on the top complaint themes.",
 "Product Quality": "Open a quality review with suppliers for the most-reported products.",
 "Features & Value": "Review pricing and feature messaging against what customers say.",
}
def dago(r): return max(0, (TODAY - dt.date.fromisoformat(r["date"])).days)
def save_issues(): json.dump(ISSUES, open(IF, "w"))

def filt(category="", sentiment="", topic="", search=""):
    s = search.lower()
    return [r for r in ROWS if (not category or r["category"] == category) and (not sentiment or r["sentiment"] == sentiment)
            and (not topic or r["topic"] == topic) and (not s or s in r["review"].lower())]

def recs():
    out = []
    for t in {r["topic"] for r in ROWS}:
        rs = [r for r in ROWS if r["topic"] == t]; ng = [r for r in rs if r["sentiment"] == "negative"]
        if not ng: continue
        rec = sum(dago(r) <= 10 for r in ng); pri = sum(10 < dago(r) <= 40 for r in ng)
        g = min(3, max(.5, (rec / 10) / max(pri / 30, .02)))
        sev = sum(r["severity"] for r in ng) / len(ng)
        trend = "rising" if g > 1.2 else "falling" if g < .8 else "stable"
        out.append({"topic": t, "negative": len(ng), "total": len(rs), "severity": round(sev, 1), "recent": rec, "prior": pri,
                    "growth": round(g, 1), "raw": len(ng) * sev * g, "action": ACTIONS.get(t, "Review these comments with the owning team."),
                    "why": f"{len(ng)} negative mentions ({round(100*len(ng)/len(rs))}% of '{t}' feedback), average severity {sev:.1f}/5, "
                           f"{rec} in the last 10 days vs {pri} in the 30 days before. Trend is {trend} (x{g:.1f})."})
    mx = max([o["raw"] for o in out] or [1])
    for o in out:
        o["score"] = round(100 * o.pop("raw") / mx); o["priority"] = "High" if o["score"] >= 66 else "Medium" if o["score"] >= 33 else "Low"
    return sorted(out, key=lambda o: -o["score"])

@app.get("/api/summary")
def summary(category: str = "", sentiment: str = "", topic: str = ""):
    rs = filt(category, sentiment, topic); c = Counter(r["sentiment"] for r in rs)
    tp = {}
    for r in rs:
        x = tp.setdefault(r["topic"], {"topic": r["topic"], "count": 0, "neg": 0}); x["count"] += 1; x["neg"] += r["sentiment"] == "negative"
    tr = {k: [0] * 8 for k in ("positive", "neutral", "negative")}
    for r in rs:
        if dago(r) < 56: tr[r["sentiment"]][7 - dago(r) // 7] += 1
    labels = [(TODAY - dt.timedelta(days=7 * w + 6)).strftime("%d %b") for w in range(7, -1, -1)]
    ht = {}
    for r in rs:
        if r["sentiment"] == "negative" and dago(r) < 56: ht.setdefault(r["topic"], [0] * 8)[7 - dago(r) // 7] += 1
    heat_rows = sorted(({"topic": k, "cells": v} for k, v in ht.items()), key=lambda x: -sum(x["cells"]))[:6]
    return {"total": len(rs), "pos": c["positive"], "neu": c["neutral"], "neg": c["negative"],
            "topics": sorted(tp.values(), key=lambda x: -x["count"]), "trend": {"labels": labels, **tr},
            "options": {"categories": sorted({r["category"] for r in ROWS}), "topics": sorted({r["topic"] for r in ROWS})},
            "heat": {"labels": labels, "rows": heat_rows}, "meta": META, "top": (recs() or [None])[0]}

@app.get("/api/feedback")
def feedback(search: str = "", category: str = "", sentiment: str = "", topic: str = "", limit: int = 40, offset: int = 0):
    rs = sorted(filt(category, sentiment, topic, search), key=lambda r: r["date"], reverse=True)
    return {"total": len(rs), "items": rs[offset:offset + limit]}

def add_rows(items):
    res = analyze_many(list({i["review"] for i in items}), {i["review"]: i["category"] for i in items})
    n = max([r["id"] for r in ROWS] or [0])
    for it in items:
        n += 1; ROWS.append({"id": n, "review": it["review"], "category": it["category"], "date": it["date"], **res[it["review"]]})
    return len(items)

@app.post("/api/feedback")
def add_feedback(b: dict = Body(...)):
    if not b.get("review", "").strip(): return {"error": "Review text is required"}
    add_rows([{"review": b["review"].strip(), "category": b.get("category") or "Product Feedback", "date": str(TODAY)}])
    return {"ok": True, "item": ROWS[-1]}

@app.post("/api/import")
async def import_csv(file: UploadFile = File(...)):
    df = pd.read_csv(io.BytesIO(await file.read())); df.columns = [c.strip().lower() for c in df.columns]
    if "review" not in df: return {"error": "CSV needs a 'review' column"}
    df = df.dropna(subset=["review"]).head(3000)
    items = [{"review": str(r["review"]), "category": str(r.get("category", "Product Feedback")),
              "date": str(r["date"])[:10] if "date" in df and pd.notna(r.get("date")) else str(TODAY)} for _, r in df.iterrows()]
    return {"added": add_rows(items)}

@app.get("/api/recommendations")
def recommendations(): return recs()

@app.get("/api/issues")
def issues(): return ISSUES

@app.post("/api/issues")
def track(b: dict = Body(...)):
    if not any(i["topic"] == b["topic"] for i in ISSUES):
        ISSUES.append({"id": len(ISSUES) + 1, "topic": b["topic"], "why": b.get("why", ""), "score": b.get("score", 0), "status": "Open", "created": str(TODAY)}); save_issues()
    return ISSUES

@app.patch("/api/issues/{iid}")
def set_status(iid: int, b: dict = Body(...)):
    for i in ISSUES:
        if i["id"] == iid: i["status"] = b["status"]
    save_issues(); return ISSUES

@app.post("/api/ask")
def ask(b: dict = Body(...)):
    q = b.get("q", "").strip(); s = summary(); rc = recs()[:4]
    ctx = (f"Total {s['total']}; positive {s['pos']}, neutral {s['neu']}, negative {s['neg']}. Topics: "
           + "; ".join(f"{t['topic']} {t['count']} mentions, {t['neg']} negative" for t in s["topics"][:8])
           + ". Priorities: " + " | ".join(f"{r['topic']} score {r['score']}: {r['why']} Action: {r['action']}" for r in rc)
           + f". Weekly negative counts, oldest to newest: {s['trend']['negative']}")
    txt = llm_text(f"You are a customer feedback analyst. Answer in at most 3 short sentences, using ONLY this data.\nData: {ctx}\nQuestion: {q}")
    if txt: return {"answer": txt, "engine": os.getenv("ANTHROPIC_API_KEY") and "Claude" or "Gemini"}
    ql = q.lower(); top = rc[0] if rc else None
    if not top: ans = "There is no negative feedback in the data yet."
    elif re.search(r"trend|week|rising|grow|spike|worse|change", ql):
        r = max(rc, key=lambda x: x["growth"]); ans = f"{r['topic']} is moving fastest (x{r['growth']}): {r['recent']} negative mentions in the last 10 days versus {r['prior']} in the 30 days before."
    elif re.search(r"fix|recommend|action|first|priorit|should", ql): ans = f"Start with {top['topic']}. {top['action']}"
    elif re.search(r"happy|positive|good|love", ql): ans = f"{round(100 * s['pos'] / max(s['total'], 1))}% of feedback is positive."
    else: ans = f"The biggest problem is {top['topic']}. {top['why']}"
    return {"answer": ans, "engine": "Rules"}

STOP = set("the and was were for with this that but they their have had not very from been your you our".split())
def toks(s): return {w for w in re.findall(r"[a-z']+", s.lower()) if len(w) > 3 and w not in STOP}

@app.get("/api/clusters")
def clusters(category: str = "", sentiment: str = "", topic: str = ""):
    """Group similar feedback by word overlap (Jaccard >= 0.5)."""
    cnt = Counter((r["review"], r["sentiment"], r["topic"]) for r in filt(category, sentiment, topic)); cl = []
    for (rev, sent, tp), n in cnt.most_common():
        t = toks(rev)
        for c in cl:
            if len(t & c["t"]) / max(len(t | c["t"]), 1) >= .5:
                c["count"] += n; c["neg"] += n if sent == "negative" else 0; c["variants"] += 1; break
        else:
            cl.append({"t": t, "label": rev, "topic": tp, "count": n, "neg": n if sent == "negative" else 0, "variants": 1})
    for c in cl: c.pop("t")
    return sorted(cl, key=lambda c: -c["count"])[:8]

DEFAULT_DS = os.getenv("ADAPTION_DATASET_ID", "40b82b47-4f93-4666-8c70-344b6cb964dd")
def _ad():
    from adaption import Adaption
    return Adaption(api_key=os.environ["ADAPTION_API_KEY"])

@app.get("/api/adaption")
def adaption_status(dataset_id: str = ""):
    try:
        d = _ad().datasets.get(dataset_id or DEFAULT_DS); ev = getattr(d, "evaluation_summary", None); pg = getattr(d, "progress", None)
        return {"live": True, "dataset_id": d.dataset_id, "status": d.status, "rows": d.row_count,
                "processed": getattr(pg, "processed_rows", None), "total": getattr(pg, "total_rows", None),
                "grade_before": getattr(ev, "grade_before", None), "grade_after": getattr(ev, "grade_after", None),
                "score_before": getattr(ev, "score_before", None), "score_after": getattr(ev, "score_after", None)}
    except Exception as e:
        return {"live": False, "error": str(e)[:200]}

@app.post("/api/adaption/start")
async def adaption_start(file: UploadFile = File(...)):
    try:
        df = pd.read_csv(io.BytesIO(await file.read())); df.columns = [c.strip().lower() for c in df.columns]
        if "review" not in df: return {"error": "CSV needs a 'review' column"}
        if "category" not in df: df["category"] = "Uncategorized"
        df = df.dropna(subset=["review"]).head(500)[["review", "category"]]
        path = os.path.join(tempfile.gettempdir(), "if_upload.csv"); df.to_csv(path, index=False)
        c = _ad(); did = c.datasets.upload_file(path, name="insightflow-upload").dataset_id
        for _ in range(15):
            if c.datasets.get(did).status == "awaiting_input": break
            time.sleep(2)
        c.datasets.run(did, column_mapping={"prompt": "review", "completion": "category"}, recipe_specification={"recipes": {"deduplication": True}})
        return {"dataset_id": did, "rows": len(df)}
    except Exception as e:
        return {"error": str(e)[:200]}

@app.post("/api/adaption/ingest")
def adaption_ingest(b: dict = Body(...)):
    try:
        c = _ad(); did = b["dataset_id"]
        if c.datasets.get(did).status != "succeeded": return {"error": "Adaption run is not finished yet"}
        resp = c.datasets.download(did, file_format="csv"); path = os.path.join(tempfile.gettempdir(), "if_adapted.csv")
        try: resp.write_to_file(path)
        except Exception: open(path, "wb").write(resp.read())
        df = pd.read_csv(path).dropna(subset=["review"])
        return {"added": add_rows([{"review": str(r["review"]), "category": str(r.get("category", "Uncategorized")), "date": str(TODAY)} for _, r in df.iterrows()])}
    except Exception as e:
        return {"error": str(e)[:200]}

@app.get("/report", response_class=HTMLResponse)
def report():
    s = summary(); m = META
    rows = "".join(f"<tr><td>{o['topic']}</td><td>{o['priority']} ({o['score']})</td><td>{o['why']}</td><td>{o['action']}</td></tr>" for o in recs()[:6])
    iss = "".join(f"<li><b>{i['topic']}</b>: {i['status']}</li>" for i in ISSUES) or "<li>No issues tracked yet.</li>"
    return f"""<!doctype html><meta charset=utf-8><title>InsightFlow report</title><style>body{{font:15px/1.5 system-ui;max-width:900px;margin:30px auto;padding:0 20px;color:#14213d}}
td,th{{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}}table{{border-collapse:collapse;width:100%}}button{{padding:8px 14px}}@media print{{button{{display:none}}}}</style>
<button onclick=print()>Print or save as PDF</button><h1>InsightFlow insight report</h1><p>Generated {TODAY}. {s['total']} feedback entries analysed:
{s['pos']} positive, {s['neu']} neutral, {s['neg']} negative ({round(100*s['neg']/max(s['total'],1))}% negative).</p>
<p>Data quality (Adaption): {m['raw_rows']} raw rows reduced to {m['adapted_rows']}; grade {m['grade_before']} to {m['grade_after']} (score {m['score_before']} to {m['score_after']}).</p>
<h2>Priority issues</h2><table><tr><th>Issue</th><th>Priority</th><th>Why it matters</th><th>Recommended action</th></tr>{rows}</table>
<h2>Tracked issues</h2><ul>{iss}</ul>"""

app.mount("/", StaticFiles(directory=os.path.join(BASE, "static"), html=True), name="static")
