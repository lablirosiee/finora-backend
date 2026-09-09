import os
from pathlib import Path

from dotenv import load_dotenv


# ============================================================
# Project Configuration
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent

load_dotenv(ROOT_DIR / ".env")


# ============================================================
# GRU Forecast Configuration
# ============================================================

MODEL_PATH = (
    ROOT_DIR
    / "models"
    / "finora_gru_model.h5"
)

SCALER_PATH = (
    ROOT_DIR
    / "models"
    / "scaler.pkl"
)


FEATURE_COLUMNS = [
    "dailyExpense",
    "remainingAllowance",
    "essentialExpense",
    "nonEssentialExpense",
    "daysUntilNextAllowance",
    "allowanceAmount",
]


SEQUENCE_LENGTH = 30

HISTORY_LENGTH = 30


# ============================================================
# Firebase Configuration
# ============================================================

FIREBASE_SERVICE_ACCOUNT_PATH = Path(
    os.getenv(
        "FIREBASE_SERVICE_ACCOUNT_PATH",
        str(
            ROOT_DIR
            / "firebase-service-account.json"
        ),
    )
)


# ============================================================
# Gmail / SMTP Configuration
# ============================================================

GMAIL_USER = os.getenv(
    "FINORA_GMAIL_USER",
    "",
).strip()


GMAIL_APP_PASSWORD = os.getenv(
    "FINORA_GMAIL_APP_PASSWORD",
    "",
).replace(
    " ",
    "",
).strip()


SMTP_HOST = "smtp.gmail.com"

SMTP_PORT = 465

SMTP_TIMEOUT_SECONDS = 20