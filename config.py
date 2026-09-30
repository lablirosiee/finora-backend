import json
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
# V9 Two-Stage GRU Forecast Configuration
# ============================================================

MODEL_DIR = (
    ROOT_DIR
    / "models"
)


CLASSIFIER_MODEL_PATH = (
    MODEL_DIR
    / "finora_depletion_classifier_v9.keras"
)


REGRESSOR_MODEL_PATH = (
    MODEL_DIR
    / "finora_depletion_regressor_v9.keras"
)


SCALER_PATH = (
    MODEL_DIR
    / "scaler_v9.pkl"
)


CLASSIFIER_THRESHOLD_PATH = (
    MODEL_DIR
    / "classifier_threshold_v9.json"
)


FORECAST_CONFIG_PATH = (
    MODEL_DIR
    / "forecast_config_v9.json"
)


# ============================================================
# V9 Feature Configuration
# ============================================================

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


# ============================================================
# V9 Classifier Threshold
# ============================================================

DEFAULT_DEPLETION_THRESHOLD = 0.42


def load_depletion_threshold() -> float:
    """
    Load the classifier threshold selected during V9 training.

    Falls back to the validated V9 threshold of 0.42 only when
    the threshold artifact does not exist.

    If the artifact exists but is invalid, startup should fail
    rather than silently using the wrong threshold.
    """

    if not CLASSIFIER_THRESHOLD_PATH.exists():
        return DEFAULT_DEPLETION_THRESHOLD

    try:
        with CLASSIFIER_THRESHOLD_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

    except Exception as exc:
        raise RuntimeError(
            "Unable to read the V9 classifier threshold file: "
            f"{CLASSIFIER_THRESHOLD_PATH}"
        ) from exc

    possible_keys = [
        "threshold",
        "classifier_threshold",
        "classifierThreshold",
        "selected_threshold",
        "selectedThreshold",
    ]

    for key in possible_keys:

        if key not in data:
            continue

        try:
            threshold = float(
                data[key]
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise RuntimeError(
                "The V9 classifier threshold is not numeric."
            ) from exc

        if not 0.0 <= threshold <= 1.0:
            raise RuntimeError(
                "The V9 classifier threshold must be "
                "between 0 and 1."
            )

        return threshold

    raise RuntimeError(
        "The V9 classifier threshold file exists, "
        "but no supported threshold field was found."
    )


DEPLETION_THRESHOLD = (
    load_depletion_threshold()
)


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