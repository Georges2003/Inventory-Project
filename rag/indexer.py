# Reads inventory Excel, converts each row to a text chunk,
# embeds via Ollama, and upserts into ChromaDB.

import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    INVENTORY_FILE,
    CHROMA_PERSIST_DIR,
    RAG_COLLECTION_NAME,
    RAG_EMBED_MODEL,
    RAG_REFRESH_INTERVAL_SECONDS,
    OLLAMA_BASE_URL,
)


# ── Custom embedding function ─────────────────────────────────────────────────
class OllamaEmbedder:
    """
    Calls Ollama embeddings API directly via requests.
    Auto-detects whether your Ollama version uses:
      - New API: POST /api/embed        { "input": "..." }  → { "embeddings": [[...]] }
      - Old API: POST /api/embeddings   { "prompt": "..." } → { "embedding": [...] }
    """
    def __init__(self, model: str, base_url: str):
        self.model     = model
        self.base_url  = base_url.rstrip("/")
        self._endpoint = None  # detected on first call

    def _detect_endpoint(self) -> str:
        """Try new API first, fall back to old."""
        # New format (Ollama >= 0.1.31)
        try:
            r = requests.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": "test"},
                timeout=15,
            )
            if r.status_code == 200 and "embeddings" in r.json():
                print(f"[Embedder] Using /api/embed (new format)")
                return "new"
        except Exception:
            pass

        # Legacy format
        try:
            r = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": "test"},
                timeout=15,
            )
            if r.status_code == 200 and "embedding" in r.json():
                print(f"[Embedder] Using /api/embeddings (legacy format)")
                return "old"
        except Exception:
            pass

        raise ConnectionError(
            f"Cannot reach Ollama at {self.base_url}.\n"
            "  1. Run: ollama serve\n"
            f"  2. Run: ollama pull {self.model}"
        )

    def _embed_one(self, text: str) -> list:
        if self._endpoint == "new":
            r = requests.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": text},
                timeout=60,
            )
            r.raise_for_status()
            emb = r.json().get("embeddings", [])
            # embeddings is a list-of-lists; return the first vector
            return emb[0] if emb and isinstance(emb[0], list) else emb
        else:
            r = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=60,
            )
            r.raise_for_status()
            return r.json().get("embedding", [])

    def __call__(self, input: list) -> list:
        if self._endpoint is None:
            self._endpoint = self._detect_endpoint()

        result = []
        for text in input:
            emb = self._embed_one(str(text))
            if not emb:
                raise ValueError(
                    f"Ollama returned an empty embedding for model '{self.model}'.\n"
                    f"Make sure the model is pulled: ollama pull {self.model}"
                )
            result.append(emb)
        return result


# ── Text conversion ───────────────────────────────────────────────────────────
def row_to_text(row: dict) -> str:
    """Convert one inventory row into a descriptive plain-English chunk."""
    stock     = int(row.get("current_stock", 0))
    threshold = int(row.get("reorder_threshold", 0))
    max_cap   = int(row.get("max_capacity", 0))
    unit_cost = float(row.get("unit_cost", 0))
    deficit   = max(0, threshold - stock)
    status    = "BELOW reorder threshold" if stock < threshold else "within safe levels"
    pct_full  = round((stock / max_cap * 100), 1) if max_cap > 0 else 0

    updated = row.get("last_updated", "unknown")
    if hasattr(updated, "strftime"):
        updated = updated.strftime("%Y-%m-%d %H:%M")

    return (
        f"Item {row.get('item_id')} ({row.get('item_name')}) is in the "
        f"{row.get('category')} category. "
        f"Current stock: {stock} units. "
        f"Reorder threshold: {threshold} units. "
        f"Max capacity: {max_cap} units ({pct_full}% full). "
        f"Stock status: {status}. "
        f"Deficit: {deficit} units below threshold. "
        f"Unit cost: ${unit_cost:.2f}. "
        f"Supplier: {row.get('supplier')}. "
        f"Last updated: {updated}."
    )


# ── ChromaDB collection ───────────────────────────────────────────────────────
def get_chroma_collection():
    import chromadb
    os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
    client     = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    embedder   = OllamaEmbedder(model=RAG_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    collection = client.get_or_create_collection(
        name=RAG_COLLECTION_NAME,
        embedding_function=embedder,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


# ── Main index function ───────────────────────────────────────────────────────
def index_inventory(verbose=True) -> dict:
    if not os.path.exists(INVENTORY_FILE):
        return {"success": False, "error": f"File not found: {INVENTORY_FILE}"}

    try:
        df = pd.read_excel(INVENTORY_FILE, engine="openpyxl")
    except Exception as e:
        return {"success": False, "error": f"Could not read Excel: {e}"}

    try:
        collection = get_chroma_collection()
    except Exception as e:
        return {"success": False, "error": str(e)}

    documents, metadatas, ids = [], [], []
    for _, row in df.iterrows():
        r       = row.to_dict()
        item_id = str(r.get("item_id", ""))
        documents.append(row_to_text(r))
        metadatas.append({
            "item_id":           item_id,
            "item_name":         str(r.get("item_name", "")),
            "category":          str(r.get("category", "")),
            "current_stock":     int(r.get("current_stock", 0)),
            "reorder_threshold": int(r.get("reorder_threshold", 0)),
            "supplier":          str(r.get("supplier", "")),
            "below_threshold":   str(
                int(r.get("current_stock", 0)) < int(r.get("reorder_threshold", 0))
            ),
        })
        ids.append(item_id)

    try:
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
    except Exception as e:
        return {"success": False, "error": f"Upsert failed: {e}"}

    flagged = sum(1 for m in metadatas if m["below_threshold"] == "True")
    ts      = datetime.now().strftime("%H:%M:%S")
    if verbose:
        print(f"[{ts}] Indexed {len(documents)} items  ({flagged} below threshold)")

    return {"success": True, "indexed": len(documents), "flagged": flagged}


# ── Loop ──────────────────────────────────────────────────────────────────────
def run_indexer_loop():
    print("=" * 55)
    print("  RAG Indexer Running")
    print(f"  Refresh every {RAG_REFRESH_INTERVAL_SECONDS}s")
    print("  Press Ctrl+C to stop")
    print("=" * 55)

    result = index_inventory()
    if not result["success"]:
        print(f"\n❌ Indexing failed: {result['error']}\n")
        sys.exit(1)

    while True:
        time.sleep(RAG_REFRESH_INTERVAL_SECONDS)
        index_inventory()


if __name__ == "__main__":
    run_indexer_loop()