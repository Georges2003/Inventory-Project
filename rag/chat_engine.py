# rag/chat_engine.py
# RAG chat engine with proper separation between:
#   - Casual conversation  → direct LLM, no inventory context injected
#   - Inventory questions  → RAG retrieval + LLM with data context

import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    CHROMA_PERSIST_DIR,
    RAG_COLLECTION_NAME,
    RAG_EMBED_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)

# ── Prompts ────────────────────────────────────────────────────────────────────

CHAT_SYSTEM = """You are a friendly and helpful inventory management assistant named Aria. 
You help operations teams with their inventory questions.
When users greet you or make small talk, respond naturally and warmly — like a helpful colleague.
Keep responses concise."""

RAG_SYSTEM = """You are an inventory analyst assistant.
You MUST answer using ONLY the inventory data chunks provided below. Do not use any prior knowledge.
Each chunk describes one inventory item with its current stock, threshold, and status.
If a chunk says 'Stock status: BELOW reorder threshold' then that item IS below threshold — list it.
Be specific: include item IDs, item names, stock numbers, and supplier names in your answer.
Never say 'no items' if any chunk contains the words 'BELOW reorder threshold'."""

# ── Inventory keywords ─────────────────────────────────────────────────────────
INVENTORY_KEYWORDS = {
    "stock","item","items","threshold","reorder","supplier","suppliers",
    "category","units","inventory","flagged","critical","low","deficit",
    "days","order","value","cost","itm","below","level","levels",
    "how many","which items","what items","list all","show all","tell me about",
    "status","health","at risk","shortage","fill","capacity","warehouse",
    "raw material","packaging","electrical","consumable","tool","tools",
}


class RAGChatEngine:

    def __init__(self):
        self.collection = self._load_collection()
        self.llm        = self._load_llm()
        self.history    = []  # [{role, content}]

    # ── Public API ─────────────────────────────────────────────────────────────

    def ask(self, question: str, n_results: int = 6) -> dict:
        if self._is_inventory_question(question):
            return self._rag_answer(question, n_results)
        else:
            return self._chat_answer(question)

    def reset_history(self):
        self.history = []

    def get_collection_stats(self) -> dict:
        if self.collection is None:
            return {"indexed": 0, "status": "unavailable"}
        try:
            return {"indexed": self.collection.count(), "status": "ready"}
        except Exception:
            return {"indexed": 0, "status": "error"}

    # ── Routing ────────────────────────────────────────────────────────────────

    def _is_inventory_question(self, text: str) -> bool:
        """Returns True only if the question is clearly about inventory data."""
        t = text.lower().strip()

        # Explicit casual phrases — always False regardless of other words
        casual = [
            "hello","hi","hey","good morning","good afternoon","good evening",
            "how are you","how r you","what's up","wassup","sup",
            "thanks","thank you","thank","great","perfect","awesome","nice",
            "bye","goodbye","see you","take care","ok","okay","sure","alright",
            "who are you","what are you","what can you do","help me",
            "what is your name","your name","introduce yourself",
        ]
        for phrase in casual:
            if t == phrase or t.startswith(phrase + " ") or t.endswith(" " + phrase):
                return False

        # Check for inventory keywords
        return any(kw in t for kw in INVENTORY_KEYWORDS)

    # ── Casual conversation path ───────────────────────────────────────────────

    def _chat_answer(self, question: str) -> dict:
        """Pure conversational reply — NO inventory data injected."""

        # Build a clean conversation history (last 6 messages)
        messages = []
        for m in self.history[-6:]:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": question})

        if self.llm is not None:
            try:
                # Build prompt with system context only — no RAG data
                history_str = ""
                if self.history:
                    history_str = "\n".join(
                        f"{m['role'].capitalize()}: {m['content']}"
                        for m in self.history[-6:]
                    )
                    history_str = f"\nPrevious messages:\n{history_str}\n"

                prompt = f"""{CHAT_SYSTEM}
{history_str}
User: {question}
Aria:"""
                response = self.llm.invoke(prompt)
                answer   = response.content.strip()
            except Exception:
                answer = self._simple_reply(question)
        else:
            answer = self._simple_reply(question)

        self.history.append({"role": "user",      "content": question})
        self.history.append({"role": "assistant",  "content": answer})

        return {"success": True, "answer": answer, "sources": [],
                "timestamp": datetime.now().isoformat()}

    def _simple_reply(self, question: str) -> str:
        """Rule-based fallback for casual chat when LLM is unavailable."""
        q = question.lower().strip()
        if any(w in q for w in ["hello","hi","hey","good morning","good afternoon","good evening"]):
            return "Hello! I'm Aria, your inventory assistant. How can I help you today?"
        if any(w in q for w in ["how are you","how r you","what's up"]):
            return "I'm doing great, ready to help! Ask me anything about your inventory."
        if any(w in q for w in ["thank","thanks"]):
            return "You're welcome! Let me know if you need anything else."
        if any(w in q for w in ["bye","goodbye","see you"]):
            return "Goodbye! Come back anytime you need inventory insights."
        if any(w in q for w in ["who are you","what are you","your name","introduce"]):
            return "I'm Aria, an AI assistant specialised in inventory management. I can answer questions about stock levels, suppliers, reorder alerts, and more."
        if any(w in q for w in ["what can you do","help"]):
            return (
                "I can help you with:\n"
                "• Which items are below their reorder threshold\n"
                "• Stock levels for specific items\n"
                "• Supplier information\n"
                "• Category health overview\n"
                "• Reorder value estimates\n\n"
                "Just ask me a question!"
            )
        return "I'm here to help with your inventory! Try asking about stock levels, flagged items, or suppliers."

    # ── RAG inventory answer path ──────────────────────────────────────────────

    def _rag_answer(self, question: str, n_results: int = 6) -> dict:
        """Retrieves relevant inventory chunks and answers with LLM."""

        if self.collection is None:
            return {
                "success": False,
                "answer": (
                    "The inventory index isn't available.\n\n"
                    "Please start:\n"
                    "• `ollama serve`\n"
                    "• `python rag/indexer.py`"
                ),
                "sources": [],
            }

        try:
            count = self.collection.count()
        except Exception as e:
            return {"success": False, "answer": f"Index error: {e}", "sources": []}

        if count == 0:
            return {
                "success": False,
                "answer": "Nothing indexed yet. Run `python rag/indexer.py` first.",
                "sources": [],
            }

        # Retrieve
        try:
            results = self.collection.query(
                query_texts=[question],
                n_results=min(n_results, count),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            msg = str(e)
            if "embedding" in msg.lower() or "ollama" in msg.lower():
                return {"success": False, "answer": (
                    "Embedding failed. Check:\n"
                    "• `ollama serve` is running\n"
                    "• `ollama pull nomic-embed-text` is done"
                ), "sources": []}
            return {"success": False, "answer": f"Retrieval error: {msg}", "sources": []}

        chunks    = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        if not chunks:
            return {"success": True,
                    "answer": "I couldn't find relevant data for that question.",
                    "sources": []}

        # ── Direct Excel answer for threshold/flagged questions ─────────────
        # Read inventory.xlsx directly — always 100% current, no index lag.
        q_lower = question.lower()
        if any(w in q_lower for w in ["below","low","flagged","threshold","critical","alert","critically"]):
            try:
                import pandas as pd
                from config.settings import INVENTORY_FILE
                df = pd.read_excel(INVENTORY_FILE, engine="openpyxl")
                flagged = df[df["current_stock"] < df["reorder_threshold"]].copy()
                if flagged.empty:
                    answer = "No items are currently below their reorder threshold."
                    sources = []
                else:
                    flagged["deficit_pct"] = ((flagged["reorder_threshold"] - flagged["current_stock"]) / flagged["reorder_threshold"] * 100).round(1)
                    flagged["urgency"] = flagged["deficit_pct"].apply(
                        lambda x: "CRITICAL" if x >= 50 else ("HIGH" if x >= 25 else "MEDIUM"))
                    uo = {"CRITICAL":0,"HIGH":1,"MEDIUM":2}
                    flagged = flagged.sort_values("deficit_pct", ascending=False)
                    lines = [
                        f"• {r['item_id']} — {r['item_name']}  "
                        f"stock: {int(r['current_stock'])} / {int(r['reorder_threshold'])}  "
                        f"supplier: {r['supplier']}  [{r['urgency']}]"
                        for _, r in flagged.iterrows()
                    ]
                    answer = (f"{len(flagged)} item(s) currently below reorder threshold:\n"
                              + "\n".join(lines))
                    sources = [{"item_id": r["item_id"], "item_name": r["item_name"], "relevance": 100}
                               for _, r in flagged.iterrows()]
                self.history.append({"role": "user",     "content": question})
                self.history.append({"role": "assistant", "content": answer})
                return {"success": True, "answer": answer, "sources": sources,
                        "timestamp": datetime.now().isoformat()}
            except Exception as e:
                pass  # fall through to normal LLM path
        # ────────────────────────────────────────────────────────────────────

        # ── Direct Excel answer for category status questions ───────────────
        CATEGORIES = {
            "raw material":  "Raw Materials",
            "raw materials": "Raw Materials",
            "packaging":     "Packaging",
            "electrical":    "Electrical",
            "consumable":    "Consumables",
            "consumables":   "Consumables",
            "tool":          "Tools",
            "tools":         "Tools",
        }
        matched_category = None
        for keyword, cat_name in CATEGORIES.items():
            if keyword in q_lower:
                matched_category = cat_name
                break

        if matched_category:
            try:
                import pandas as pd
                from config.settings import INVENTORY_FILE
                df = pd.read_excel(INVENTORY_FILE, engine="openpyxl")
                cat_df = df[df["category"] == matched_category].copy()
                if cat_df.empty:
                    answer = f"No items found in the {matched_category} category."
                    sources = []
                else:
                    lines = []
                    for _, r in cat_df.iterrows():
                        below = r["current_stock"] < r["reorder_threshold"]
                        status = "⚠ BELOW THRESHOLD" if below else "OK"
                        lines.append(
                            f"• {r['item_id']} — {r['item_name']}  "
                            f"stock: {int(r['current_stock'])} / {int(r['reorder_threshold'])}  "
                            f"supplier: {r['supplier']}  [{status}]"
                        )
                    flagged_count = int((cat_df["current_stock"] < cat_df["reorder_threshold"]).sum())
                    answer = (f"{matched_category} — {len(cat_df)} items "
                              f"({flagged_count} below threshold):\n" + "\n".join(lines))
                    sources = [{"item_id": r["item_id"], "item_name": r["item_name"], "relevance": 100}
                               for _, r in cat_df.iterrows()]
                self.history.append({"role": "user",     "content": question})
                self.history.append({"role": "assistant", "content": answer})
                return {"success": True, "answer": answer, "sources": sources,
                        "timestamp": datetime.now().isoformat()}
            except Exception:
                pass  # fall through to normal LLM path
        # ────────────────────────────────────────────────────────────────────

        context = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(chunks))

        # Include recent conversation history for follow-ups
        history_str = ""
        if self.history:
            history_str = "\nRecent conversation:\n" + "\n".join(
                f"{m['role'].capitalize()}: {m['content']}"
                for m in self.history[-4:]
            ) + "\n"

        prompt = f"""{RAG_SYSTEM}

Inventory data:
{context}
{history_str}
User question: {question}

Answer:"""

        if self.llm is None:
            answer = self._fallback_rag_answer(question, chunks, metadatas)
        else:
            try:
                response = self.llm.invoke(prompt)
                answer   = response.content.strip()
            except Exception:
                answer = self._fallback_rag_answer(question, chunks, metadatas)

        self.history.append({"role": "user",      "content": question})
        self.history.append({"role": "assistant",  "content": answer})

        sources = [
            {"item_id": m.get("item_id",""), "item_name": m.get("item_name",""),
             "relevance": round((1 - d) * 100, 1)}
            for m, d in zip(metadatas, distances)
        ]

        return {"success": True, "answer": answer, "sources": sources,
                "timestamp": datetime.now().isoformat()}

    # ── Loaders ────────────────────────────────────────────────────────────────

    def _load_collection(self):
        try:
            import chromadb
            from rag.indexer import OllamaEmbedder
            os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
            client     = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
            embedder   = OllamaEmbedder(model=RAG_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
            collection = client.get_or_create_collection(
                name=RAG_COLLECTION_NAME,
                embedding_function=embedder,
                metadata={"hnsw:space": "cosine"},
            )
            print(f"✅ RAG: {collection.count()} items indexed")
            return collection
        except Exception as e:
            print(f"⚠️  RAG: {e}")
            return None

    def _load_llm(self):
        try:
            from langchain_ollama import ChatOllama
            llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.4)
            print(f"✅ LLM: {OLLAMA_MODEL} loaded")
            return llm
        except Exception as e:
            print(f"⚠️  LLM: {e}")
            return None

    # ── Fallback RAG answer ────────────────────────────────────────────────────

    def _fallback_rag_answer(self, question: str, chunks: list, metadatas: list) -> str:
        """
        Clean formatted fallback used when the LLM is unavailable.
        Always returns a readable table — never raw chunk text.
        """
        q = question.lower()

        # Threshold / flagged questions
        if any(w in q for w in ["below","low","flagged","threshold","critical","risk","alert","critically"]):
            flagged = [m for m in metadatas if m.get("below_threshold") == "True"]
            if not flagged:
                return "No items are currently below their reorder threshold."
            lines = [f"• {m['item_id']} — {m['item_name']}  (stock: {m['current_stock']}, threshold: {m['reorder_threshold']}, supplier: {m['supplier']})"
                     for m in flagged]
            return f"{len(flagged)} item(s) below reorder threshold:\n" + "\n".join(lines)

        # Supplier questions
        if "supplier" in q or "supplies" in q or "who supply" in q:
            lines = [f"• {m['item_id']} — {m['item_name']}: supplied by {m['supplier']}"
                     for m in metadatas[:8]]
            return "Supplier information:\n" + "\n".join(lines)

        # Category status questions — "show me all raw materials", "category status" etc.
        if any(w in q for w in ["raw material","packaging","electrical","consumable","tool","category","all","status","show"]):
            lines = [
                f"• {m['item_id']} — {m['item_name']}  "
                f"stock: {m['current_stock']} / {m['reorder_threshold']}  "
                f"{'⚠ BELOW THRESHOLD' if m.get('below_threshold')=='True' else 'OK'}"
                for m in metadatas
            ]
            return "Inventory status for retrieved items:\n" + "\n".join(lines)

        # Stock level questions
        if any(w in q for w in ["stock","units","how many","quantity","level","how much"]):
            lines = [f"• {m['item_id']} — {m['item_name']}: {m['current_stock']} units (min: {m['reorder_threshold']})"
                     for m in metadatas[:8]]
            return "Stock levels:\n" + "\n".join(lines)

        # Default — build a clean summary from metadata instead of dumping raw chunk
        lines = [
            f"• {m['item_id']} — {m['item_name']}  "
            f"stock: {m['current_stock']} / {m['reorder_threshold']}  "
            f"supplier: {m['supplier']}"
            for m in metadatas[:6]
        ]
        return "Here is the relevant inventory data:\n" + "\n".join(lines)