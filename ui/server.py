# FastAPI backend — serves inventory data as JSON + the HTML frontend
# Run with: python ui/server.py
# Opens at: http://localhost:8000

import os
import sys
from datetime import datetime
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("\n❌ FastAPI or Uvicorn not installed.")
    print("   Run: pip install fastapi uvicorn\n")
    sys.exit(1)

import pandas as pd
from config.settings import INVENTORY_FILE

app = FastAPI(title="Inventory Monitor API")

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Lazy-load RAG engine
_rag_engine = None

def get_rag():
    global _rag_engine
    if _rag_engine is None:
        try:
            from rag.chat_engine import RAGChatEngine
            _rag_engine = RAGChatEngine()
        except Exception as e:
            print(f"⚠️  RAG unavailable: {e}")
    return _rag_engine


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_inventory() -> pd.DataFrame:
    if not os.path.exists(INVENTORY_FILE):
        return pd.DataFrame()
    return pd.read_excel(INVENTORY_FILE, engine="openpyxl")


def serialize_row(row) -> dict:
    d = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif hasattr(v, "item"):
            d[k] = v.item()
        else:
            d[k] = v
    return d


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    df = load_inventory()
    if df.empty:
        return {"total":0,"safe":0,"flagged":0,"critical":0,"health_pct":100,"reorder_value":0}
    flagged = df[df["current_stock"] < df["reorder_threshold"]]
    n = len(df); f = len(flagged)
    cr = 0
    rv = 0
    medium = 0
    if not flagged.empty:
        pcts = (flagged["reorder_threshold"] - flagged["current_stock"]) / flagged["reorder_threshold"] * 100
        cr     = int((pcts >= 50).sum())
        medium = int((pcts < 25).sum())
        rv     = float(flagged.apply(
            lambda r: max(0, int(r["max_capacity"]*0.8) - int(r["current_stock"])) * float(r["unit_cost"]),
            axis=1).sum())
    return {
        "total":         n,
        "safe":          n - f,
        "flagged":       f,
        "critical":      cr,
        "medium":        medium,
        "health_pct":    round((n-f)/n*100, 1) if n > 0 else 100,
        "reorder_value": round(rv, 2),
        "timestamp":     datetime.now().isoformat(),
    }


@app.get("/api/inventory")
def get_inventory(category: Optional[str]=None, status: Optional[str]=None, search: Optional[str]=None):
    df = load_inventory()
    if df.empty: return []
    if category and category != "all":
        df = df[df["category"] == category]
    if status == "flagged":
        df = df[df["current_stock"] < df["reorder_threshold"]]
    elif status == "safe":
        df = df[df["current_stock"] >= df["reorder_threshold"]]
    if search:
        mask = (df["item_name"].str.contains(search, case=False, na=False) |
                df["item_id"].str.contains(search, case=False, na=False))
        df = df[mask]
    all_df = load_inventory()
    flagged_ids = set(all_df[all_df["current_stock"] < all_df["reorder_threshold"]]["item_id"].tolist())
    result = []
    for _, row in df.iterrows():
        r = serialize_row(row)
        r["is_flagged"] = r["item_id"] in flagged_ids
        r["fill_pct"]   = round(r["current_stock"] / r["max_capacity"] * 100, 1) if r.get("max_capacity",0) > 0 else 0
        result.append(r)
    return result


@app.get("/api/flagged")
def get_flagged():
    df = load_inventory()
    if df.empty: return []
    f = df[df["current_stock"] < df["reorder_threshold"]].copy()
    if f.empty: return []
    f["deficit"]     = f["reorder_threshold"] - f["current_stock"]
    f["deficit_pct"] = (f["deficit"] / f["reorder_threshold"] * 100).round(1)
    f["urgency"]     = f["deficit_pct"].apply(
        lambda x: "CRITICAL" if x>=50 else ("HIGH" if x>=25 else "MEDIUM"))
    f["days_left"]   = (f["current_stock"] / (f["reorder_threshold"] * 0.05)).round(1)
    uo = {"CRITICAL":0,"HIGH":1,"MEDIUM":2}
    f["_u"] = f["urgency"].map(uo)
    f = f.sort_values(["_u","deficit_pct"], ascending=[True,False]).drop("_u", axis=1)
    return [serialize_row(row) for _, row in f.iterrows()]


@app.get("/api/categories")
def get_categories():
    df = load_inventory()
    if df.empty: return []
    result = []
    for cat, g in df.groupby("category"):
        flagged = int((g["current_stock"] < g["reorder_threshold"]).sum())
        total   = len(g)
        result.append({
            "name":       cat,
            "total":      total,
            "flagged":    flagged,
            "safe":       total - flagged,
            "health_pct": round((total-flagged)/total*100, 1),
        })
    return result


class ChatRequest(BaseModel):
    message: str
    history: list = []


@app.post("/api/chat")
def chat(req: ChatRequest):
    # Reset signal from clear button
    if req.message == "__reset__":
        engine = get_rag()
        if engine:
            engine.reset_history()
        return {"answer":"", "sources":[], "success":True}
    engine = get_rag()
    if engine is None:
        return {
            "answer":  "Aura is not available. Make sure Ollama is running and rag/indexer.py has been started.",
            "sources": [], "success": False,
        }
    result = engine.ask(req.message)
    return result


@app.get("/api/rag-status")
def rag_status():
    engine = get_rag()
    if engine is None:
        return {"status": "unavailable", "indexed": 0}
    return engine.get_collection_stats()


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>Frontend not found.</h1>", status_code=404)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser, threading, time

    print("=" * 55)
    print("  Inventory Monitor — Web Server")
    print("  http://localhost:8000")
    print("  Press Ctrl+C to stop")
    print("=" * 55)

    # Auto-open browser after short delay
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000")
    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")