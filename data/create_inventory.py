# data/create_inventory.py
# Run this ONCE to create the initial inventory.xlsx with seed data

import pandas as pd
import os
from datetime import datetime

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
INVENTORY_FILE = os.path.join(DATA_DIR, "inventory.xlsx")


def create_inventory():
    items = [
        # --- Raw Materials ---
        ("ITM-001", "Steel Bolts M8",         "Raw Materials",  320, 50,  500, 0.15,  "FastenCo"),
        ("ITM-002", "Steel Bolts M12",        "Raw Materials",  280, 60,  400, 0.22,  "FastenCo"),
        ("ITM-003", "Copper Wire 2mm",         "Raw Materials",   95, 100, 300, 1.80,  "WireTech"),
        ("ITM-004", "Copper Wire 4mm",         "Raw Materials",  140, 80,  250, 2.40,  "WireTech"),
        ("ITM-005", "Aluminium Sheet 1mm",     "Raw Materials",   55, 40,  150, 8.50,  "MetalWorks"),
        ("ITM-006", "Aluminium Sheet 2mm",     "Raw Materials",   70, 40,  150, 12.00, "MetalWorks"),
        ("ITM-007", "Stainless Rods 6mm",      "Raw Materials",  200, 75,  400, 3.20,  "SteelPro"),
        ("ITM-008", "Carbon Steel Plate",      "Raw Materials",   30, 25,  100, 45.00, "SteelPro"),
        ("ITM-009", "Rubber Gaskets 50mm",     "Raw Materials",  410, 100, 600, 0.80,  "SealMasters"),
        ("ITM-010", "Rubber Gaskets 100mm",    "Raw Materials",  180, 80,  400, 1.50,  "SealMasters"),

        # --- Packaging ---
        ("ITM-011", "Cardboard Box A4",        "Packaging",      900, 200, 2000, 0.30, "PackCo"),
        ("ITM-012", "Cardboard Box A3",        "Packaging",      620, 150, 1500, 0.45, "PackCo"),
        ("ITM-013", "Bubble Wrap Roll 50m",    "Packaging",       18, 10,   50,  14.00, "WrapIt"),
        ("ITM-014", "Packing Tape 48mm",       "Packaging",       95, 30,  200,  2.80, "PackCo"),
        ("ITM-015", "Foam Insert Sheet",       "Packaging",      160, 50,  300,  3.50, "FoamTech"),
        ("ITM-016", "Shrink Wrap Roll",        "Packaging",       22, 15,   80,  18.00, "WrapIt"),
        ("ITM-017", "Pallet Wrap Film",        "Packaging",       40, 20,  100,  22.00, "WrapIt"),
        ("ITM-018", "Corrugated Dividers",     "Packaging",      310, 100, 500,  0.90, "PackCo"),

        # --- Tools ---
        ("ITM-019", "Safety Gloves L",         "Tools",          85, 30,  200,  4.50, "SafetyFirst"),
        ("ITM-020", "Safety Gloves XL",        "Tools",          60, 30,  200,  4.50, "SafetyFirst"),
        ("ITM-021", "Safety Goggles",          "Tools",          45, 20,  100,  8.00, "SafetyFirst"),
        ("ITM-022", "Hard Hat Yellow",         "Tools",          28, 15,   80,  12.00, "SafetyFirst"),
        ("ITM-023", "Torque Wrench 25Nm",      "Tools",          12, 5,    30,  85.00, "ToolMaster"),
        ("ITM-024", "Hex Key Set",             "Tools",          35, 10,   60,  22.00, "ToolMaster"),
        ("ITM-025", "Calipers Digital",        "Tools",           8, 4,    20, 120.00, "PrecisionCo"),
        ("ITM-026", "Spirit Level 600mm",      "Tools",          14, 5,    30,  35.00, "ToolMaster"),

        # --- Electrical ---
        ("ITM-027", "Cable Tie 100mm Bag",     "Electrical",    500, 100, 1000,  2.50, "ElecSupply"),
        ("ITM-028", "Cable Tie 200mm Bag",     "Electrical",    320, 80,  800,   3.20, "ElecSupply"),
        ("ITM-029", "Heat Shrink Tube 3mm",    "Electrical",    180, 60,  400,   4.80, "ElecSupply"),
        ("ITM-030", "Heat Shrink Tube 6mm",    "Electrical",    140, 60,  400,   5.50, "ElecSupply"),
        ("ITM-031", "Terminal Block 12-way",   "Electrical",     55, 25,  150,  14.00, "CircuitPro"),
        ("ITM-032", "Fuse 5A Pack",            "Electrical",     90, 40,  200,   3.00, "CircuitPro"),
        ("ITM-033", "Fuse 10A Pack",           "Electrical",     70, 40,  200,   3.00, "CircuitPro"),
        ("ITM-034", "DIN Rail 1m",             "Electrical",     22, 10,   60,  18.00, "CircuitPro"),

        # --- Consumables ---
        ("ITM-035", "WD-40 500ml",             "Consumables",    48, 20,  100,   9.00, "LubriTech"),
        ("ITM-036", "Machine Oil 1L",          "Consumables",    35, 15,   80,  12.00, "LubriTech"),
        ("ITM-037", "Cutting Fluid 5L",        "Consumables",    10, 8,    40,  35.00, "LubriTech"),
        ("ITM-038", "Cleaning Solvent 1L",     "Consumables",    55, 20,  120,  15.00, "ChemClean"),
        ("ITM-039", "Anti-Corrosion Spray",    "Consumables",    25, 12,   60,  11.00, "ChemClean"),
        ("ITM-040", "Thread Sealant Tape",     "Consumables",   120, 40,  250,   1.50, "SealMasters"),
    ]

    columns = [
        "item_id", "item_name", "category",
        "current_stock", "reorder_threshold", "max_capacity",
        "unit_cost", "supplier", "last_updated"
    ]

    now = datetime.now()
    rows = []
    for item in items:
        rows.append(list(item) + [now])

    df = pd.DataFrame(rows, columns=columns)

    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_excel(INVENTORY_FILE, index=False, engine="openpyxl")
    print(f"✅ Created inventory.xlsx with {len(df)} items at:")
    print(f"   {INVENTORY_FILE}")

    # Print a summary by category
    print("\nCategory summary:")
    summary = df.groupby("category").agg(
        items=("item_id", "count"),
        below_threshold=("current_stock", lambda x: (x < df.loc[x.index, "reorder_threshold"]).sum())
    )
    print(summary.to_string())


if __name__ == "__main__":
    create_inventory()
