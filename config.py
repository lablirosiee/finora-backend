import os
from pathlib import Path

from dotenv import load_dotenv


# ============================================================
# Project Configuration
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent

load_dotenv(
    ROOT_DIR / ".env"
)


# ============================================================
# V8 Two-Stage GRU Forecast Configuration
# ============================================================

CLASSIFIER_MODEL_PATH = (
    ROOT_DIR
    / "models"
    / "finora_depletion_classifier.h5"
)

REGRESSOR_MODEL_PATH = (
    ROOT_DIR
    / "models"
    / "finora_depletion_regressor.h5"
)

SCALER_PATH = (
    ROOT_DIR
    / "models"
    / "scaler_v8.pkl"
)


FEATURE_COLUMNS = [
    "transactionAmount",
    "remainingAllowance",
    "essentialExpense",
    "nonEssentialExpense",
    "daysSincePreviousExpense",
    "daysUntilNextAllowance",
    "allowanceAmount",
    "percentageAllowanceUsed",
]


MIN_DISTINCT_EXPENSE_DAYS = 3

MIN_TRANSACTIONS = 5

MAX_SEQUENCE_LENGTH = 10

MASK_VALUE = -1.0

DEPLETION_THRESHOLD = 0.21


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