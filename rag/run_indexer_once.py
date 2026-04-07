# rag/run_index_once.py
# Called by start.bat at startup.
# Wipes the existing ChromaDB collection and rebuilds it fresh
# from the current inventory.xlsx so Aura always has accurate data.

import sys, os, shutil
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import CHROMA_PERSIST_DIR, RAG_COLLECTION_NAME

# ── Wipe old ChromaDB so stale embeddings can't cause wrong answers ──
if os.path.exists(CHROMA_PERSIST_DIR):
    shutil.rmtree(CHROMA_PERSIST_DIR)
    print("Cleared old ChromaDB index.")

os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)

# ── Re-index from scratch ──
from rag.indexer import index_inventory

result = index_inventory(verbose=True)
if not result['success']:
    print("ERROR: " + result.get('error', 'unknown'))
    sys.exit(1)

print("Done — indexed " + str(result['indexed']) + " items, " +
      str(result['flagged']) + " below threshold.")