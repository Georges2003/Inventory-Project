# Inventory Monitoring System

A multi-agent AI system for proactive inventory management.
Built with Python, LangChain, Ollama (LLaMA 3.1), ChromaDB, FastAPI, and pure HTML/CSS/JS.

---

## What It Does

Instead of waiting for someone to notice stock is low, this system:
- **Watches** a live Excel inventory file continuously
- **Detects** when any item drops below its reorder threshold
- **Analyses** the breach — calculates deficit, days until stockout, recommended order quantity
- **Generates** a professional PDF alert report automatically
- **Emails** the report directly to the operations manager via Gmail
- **Answers** plain-English questions about stock levels via an AI chat assistant (Aura)

---

## Setup

### 1. Install Ollama
Download from https://ollama.com and install.
Then pull the required models:
```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```
Note: Ollama starts automatically on Windows after installation. If you see
"address already in use" when running `ollama serve`, it is already running — that is fine.

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Create the inventory file
```bash
python data/create_inventory.py
```

### 4. Configure your environment
Edit the `.env` file in the project root:
```
GMAIL_SENDER=your_gmail@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
OPS_MANAGER_EMAIL=recipient@yourcompany.com
```

How to get a Gmail App Password:
1. Go to myaccount.google.com
2. Security → 2-Step Verification (must be enabled first)
3. Search "App Passwords" → create one for Mail
4. Copy the 16-character password into .env

---

## Running the System

### Option A — One click (recommended)
Double-click **`start.bat`** from the `inventory_system` folder.

This opens 4 terminal windows automatically and launches the browser at `http://localhost:8000`.

To stop everything, double-click **`stop.bat`**.

### Option B — Manual (4 terminals)

```bash
# Terminal 1 — Simulator (mimics live stock consumption)
python data/simulator.py

# Terminal 2 — RAG Indexer (keeps ChromaDB in sync with Excel)
python rag/indexer.py

# Terminal 3 — Orchestrator (monitors for breaches, triggers alerts)
python agents/orchestrator.py

# Terminal 4 — Web Server (dashboard + Aura chat)
python ui/server.py
```

Then open `http://localhost:8000` in your browser.

### Trigger a manual weekly report
```bash
python main.py weekly
```

---

## Testing a breach

Create `force_breach.py` in the project root:
```python
import pandas as pd
from datetime import datetime
from config.settings import INVENTORY_FILE

df = pd.read_excel(INVENTORY_FILE, engine="openpyxl")
df.loc[df["item_id"] == "ITM-001", "current_stock"] = 10
df.loc[df["item_id"] == "ITM-019", "current_stock"] = 5
df["last_updated"] = datetime.now()
df.to_excel(INVENTORY_FILE, index=False, engine="openpyxl")
print("Forced ITM-001 and ITM-019 below threshold")
```
```bash
python force_breach.py
```
With the Orchestrator running, you should receive an alert email within 30 seconds.

---

## Project Structure

```
inventory_system/
├── start.bat                  — Double-click to start everything
├── stop.bat                   — Double-click to stop everything
├── .env                       — Gmail credentials (never commit this)
├── requirements.txt
├── README.md
│
├── data/
│   ├── inventory.xlsx         — Live inventory file (auto-created)
│   ├── create_inventory.py    — Seed data generator (run once)
│   └── simulator.py           — Stock consumption simulator
│
├── agents/
│   ├── orchestrator.py        — Central decision-maker, polling loop
│   ├── monitor_agent.py       — Reads Excel, detects threshold breaches
│   ├── analysis_agent.py      — Calculates metrics + LLM insights
│   ├── report_writer.py       — Generates professional PDF reports
│   └── delivery_agent.py      — Sends reports via Gmail SMTP
│
├── rag/
│   ├── indexer.py             — Embeds inventory rows into ChromaDB
│   └── chat_engine.py         — RAG query engine + conversational AI (Aura)
│
├── ui/
│   ├── server.py              — FastAPI backend (REST API + serves frontend)
│   └── static/
│       └── index.html         — Full dashboard (HTML/CSS/JS, no framework)
│
├── config/
│   └── settings.py            — All configuration in one place
│
└── reports/                   — Generated PDF reports saved here
    └── delivery_log/          — Local delivery logs (when Gmail not configured)
```

---

## How Each Alert Works

```
Excel file updated by simulator
        ↓
Monitor Agent detects breach (polls every 30s)
        ↓
Orchestrator prioritises by severity (CRITICAL → HIGH → MEDIUM)
        ↓
Analysis Agent calculates deficit, days until stockout, recommended order
        ↓
Report Writer generates professional PDF (KPI cards, tables, AI insight)
        ↓
Delivery Agent sends email via Gmail with PDF attached
        ↓
Operations manager receives alert within ~1 minute of stock dropping
```

---

## Tech Stack

| Component        | Tool                                      |
|------------------|-------------------------------------------|
| Agent logic      | Python + LangChain                        |
| LLM              | Ollama + LLaMA 3.1 (local, free)          |
| Embeddings       | Ollama + nomic-embed-text (local, free)   |
| Vector store     | ChromaDB                                  |
| Data layer       | Pandas + OpenPyXL                         |
| PDF reports      | ReportLab                                 |
| Email delivery   | Gmail SMTP (smtplib, built-in)            |
| Web backend      | FastAPI + Uvicorn                         |
| Web frontend     | Pure HTML / CSS / JavaScript (no framework)|
| AI Chat (Aura)   | RAG pipeline — ChromaDB + LLaMA 3.1       |

Everything runs locally — zero API costs, no paid services required.
