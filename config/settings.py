# config/settings.py
# Central configuration for the Inventory Monitoring System

import os
from dotenv import load_dotenv

load_dotenv()

# --- File Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

INVENTORY_FILE = os.path.join(DATA_DIR, "inventory.xlsx")

# --- Ollama / LLM Settings ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1"  # Change to "mistral" if preferred

# --- Monitor Agent Settings ---
POLL_INTERVAL_SECONDS = 30       # How often the Monitor Agent checks the file
SIMULATOR_INTERVAL_SECONDS = 10  # How often the simulator updates stock (~2 min)

# --- Analysis Settings ---
CRITICAL_DEFICIT_PERCENT = 50    # If stock is >50% below threshold → CRITICAL
HIGH_DEFICIT_PERCENT = 25        # If stock is 25-50% below threshold → HIGH

# --- RAG Settings ---
CHROMA_PERSIST_DIR = os.path.join(BASE_DIR, "rag", "chroma_db")
RAG_COLLECTION_NAME = "inventory_chunks"
RAG_EMBED_MODEL = "nomic-embed-text"  # Free Ollama embedding model
RAG_REFRESH_INTERVAL_SECONDS = 10   # Re-index every 20s so new breaches appear quickly

# --- Gmail SMTP Settings ---
GMAIL_SENDER   = os.getenv("GMAIL_SENDER", "")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# --- Report Settings ---
OPERATIONS_MANAGER_EMAIL = os.getenv("OPS_MANAGER_EMAIL", "manager@company.com")