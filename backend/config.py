"""
FinSight — AI Financial Intelligence Platform
Application configuration.
"""

import os
from pathlib import Path

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent          # …/FinSight
configured_db_path = os.getenv("FINSIGHT_DB_PATH")
DB_PATH = (
    Path(configured_db_path).expanduser()
    if configured_db_path
    else BASE_DIR / "data" / "finsight.db"
)
DATA_DIR = DB_PATH.parent
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# ──────────────────────────────────────────────
# App metadata
# ──────────────────────────────────────────────
APP_NAME = "FinSight"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = (
    "AI Financial Intelligence Platform — Phase 1 Backend Foundation"
)

# ──────────────────────────────────────────────
# Dataset label
# ──────────────────────────────────────────────
DATASET_LABEL = "SYNTHETIC DEMO DATA"
FORECAST_LABEL = "FORECAST — NOT ACTUAL"
