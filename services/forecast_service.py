import pickle

from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Tuple
from zoneinfo import ZoneInfo

import numpy as np
from tensorflow.keras.models import load_model

from config import (
    CLASSIFIER_MODEL_PATH,
    REGRESSOR_MODEL_PATH,
    SCALER_PATH,
)

from schemas.forecast_schemas import (
    ForecastRequest,
    ForecastResponse,
)


# ============================================================
# GRU Configuration
# ============================================================

MIN_DISTINCT_EXPENSE_DAYS = 3
MIN_TRANSACTIONS = 5
MAX_SEQUENCE_LENGTH = 10

MASK_VALUE = -1.0

DEPLETION_THRESHOLD = 0.21


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


# ============================================================
# Load V8 Models and Scaler
# ============================================================

def load_model_artifacts() -> Tuple[
    Any,
    Any,
    Any,
]:

    if not CLASSIFIER_MODEL_PATH.exists():
        raise FileNotFoundError(
            "Classifier model not found: "
            f"{CLASSIFIER_MODEL_PATH}"
        )

    if not REGRESSOR_MODEL_PATH.exists():
        raise FileNotFoundError(
            "Regressor model not found: "
            f"{REGRESSOR_MODEL_PATH}"
        )

    if not SCALER_PATH.exists():
        raise FileNotFoundError(
            f"Scaler not found: {SCALER_PATH}"
        )

    classifier = load_model(
        str(CLASSIFIER_MODEL_PATH),
        compile=False,
    )

    regressor = load_model(
        str(REGRESSOR_MODEL_PATH),
        compile=False,
    )

    with SCALER_PATH.open("rb") as file:
        scaler = pickle.load(file)

    return (
        classifier,
        regressor,
        scaler,
    )


# ============================================================
# Cache Models and Scaler
# ============================================================

@lru_cache(maxsize=1)
def get_artifacts() -> Tuple[
    Any,
    Any,
    Any,
]:

    return load_model_artifacts()


# ============================================================
# Validate Transaction History
# ============================================================

def validate_history(
    request: ForecastRequest,
) -> None:

    history = request.recentHistory

    history_length = len(history)

    if history_length < MIN_TRANSACTIONS:
        raise ValueError(
            "Forecast requires at least "
            f"{MIN_TRANSACTIONS} expense transactions. "
            f"Received: {history_length}."
        )

    if history_length > MAX_SEQUENCE_LENGTH:
        raise ValueError(
            "Forecast accepts at most "
            f"{MAX_SEQUENCE_LENGTH} recent transactions. "
            f"Received: {history_length}."
        )

    distinct_expense_days = len(
        {
            entry.date
            for entry in history
        }
    )

    if (
        distinct_expense_days
        < MIN_DISTINCT_EXPENSE_DAYS
    ):
        raise ValueError(
            "Forecast requires expenses from at least "
            f"{MIN_DISTINCT_EXPENSE_DAYS} distinct "
            "calendar days. "
            f"Received: {distinct_expense_days}."
        )

    dates = [
        entry.date
        for entry in history
    ]

    if dates != sorted(dates):
        raise ValueError(
            "recentHistory must be ordered "
            "chronologically from oldest "
            "to newest transaction."
        )


# ============================================================
# Verify Scaler
# ============================================================

def verify_scaler(
    scaler,
) -> None:

    scaler_feature_count = getattr(
        scaler,
        "n_features_in_",
        None,
    )

    if (
        scaler_feature_count is not None
        and scaler_feature_count
        != len(FEATURE_COLUMNS)
    ):
        raise RuntimeError(
            "Scaler feature count mismatch. "
            f"Scaler expects "
            f"{scaler_feature_count}, "
            f"backend provides "
            f"{len(FEATURE_COLUMNS)}."
        )


# ============================================================
# Verify Model Input Shape
# ============================================================

def verify_model_shape(
    model,
    model_name: str,
) -> None:

    model_shape = model.input_shape

    if len(model_shape) != 3:
        raise RuntimeError(
            f"{model_name} has unexpected "
            f"input shape: {model_shape}"
        )

    expected_sequence_length = (
        model_shape[1]
    )

    expected_feature_count = (
        model_shape[2]
    )

    if (
        expected_sequence_length is not None
        and expected_sequence_length
        != MAX_SEQUENCE_LENGTH
    ):
        raise RuntimeError(
            f"{model_name} sequence length "
            "mismatch. "
            f"Model expects "
            f"{expected_sequence_length}, "
            f"backend provides "
            f"{MAX_SEQUENCE_LENGTH}."
        )

    if (
        expected_feature_count is not None
        and expected_feature_count
        != len(FEATURE_COLUMNS)
    ):
        raise RuntimeError(
            f"{model_name} feature count "
            "mismatch. "
            f"Model expects "
            f"{expected_feature_count}, "
            f"backend provides "
            f"{len(FEATURE_COLUMNS)}."
        )


# ============================================================
# Build GRU Input Sequence
# ============================================================

def build_input_sequence(
    request: ForecastRequest,
    scaler,
) -> np.ndarray:

    validate_history(request)

    verify_scaler(scaler)

    raw_sequence = np.asarray(
        [
            [
                entry.transactionAmount,
                entry.remainingAllowance,
                entry.essentialExpense,
                entry.nonEssentialExpense,
                entry.daysSincePreviousExpense,
                entry.daysUntilNextAllowance,
                entry.allowanceAmount,
                entry.percentageAllowanceUsed,
            ]
            for entry in request.recentHistory
        ],
        dtype=np.float32,
    )

    expected_raw_shape = (
        len(request.recentHistory),
        len(FEATURE_COLUMNS),
    )

    if raw_sequence.shape != expected_raw_shape:
        raise RuntimeError(
            "Unexpected raw input shape: "
            f"{raw_sequence.shape}. "
            f"Expected: {expected_raw_shape}."
        )

    # ========================================================
    # Scale REAL transaction rows only
    #
    # IMPORTANT:
    # Padding must happen AFTER MinMax scaling.
    # ========================================================

    try:
        scaled_sequence = scaler.transform(
            raw_sequence
        ).astype(np.float32)

    except Exception as exc:
        raise ValueError(
            f"Scaler transform failed: {exc}"
        ) from exc

    # ========================================================
    # Right-pad to 10 transactions
    #
    # Example with 5 transactions:
    #
    # TX1
    # TX2
    # TX3
    # TX4
    # TX5
    # PAD
    # PAD
    # PAD
    # PAD
    # PAD
    # ========================================================

    padded_sequence = np.full(
        (
            MAX_SEQUENCE_LENGTH,
            len(FEATURE_COLUMNS),
        ),
        MASK_VALUE,
        dtype=np.float32,
    )

    sequence_length = len(
        scaled_sequence
    )

    padded_sequence[
        :sequence_length
    ] = scaled_sequence

    return padded_sequence


# ============================================================
# Risk Level
# ============================================================

def calculate_risk_level(
    depletion_expected: bool,
    predicted_days: int | None,
) -> str:

    if not depletion_expected:
        return "LOW"

    if predicted_days is None:
        return "UNKNOWN"

    if predicted_days <= 3:
        return "CRITICAL"

    if predicted_days <= 7:
        return "HIGH"

    if predicted_days <= 14:
        return "MODERATE"

    return "LOW"


# ============================================================
# Generate Forecast
# ============================================================

def generate_forecast(
    request: ForecastRequest,
) -> ForecastResponse:

    (
        classifier,
        regressor,
        scaler,
    ) = get_artifacts()

    verify_model_shape(
        classifier,
        "Classifier",
    )

    verify_model_shape(
        regressor,
        "Regressor",
    )

    padded_sequence = build_input_sequence(
        request,
        scaler,
    )

    # ========================================================
    # GRU input
    #
    # Shape:
    # (batch, sequence, features)
    #
    # V8 Finora:
    # (1, 10, 8)
    # ========================================================

    model_input = padded_sequence.reshape(
        1,
        MAX_SEQUENCE_LENGTH,
        len(FEATURE_COLUMNS),
    )

    # ========================================================
    # Latest Transaction State
    # ========================================================

    latest_entry = (
        request.recentHistory[-1]
    )

    days_until_next_allowance = (
        latest_entry.daysUntilNextAllowance
    )

    philippine_today = datetime.now(
        ZoneInfo("Asia/Manila")
    ).date()

    next_allowance_date = (
        philippine_today
        + timedelta(
            days=days_until_next_allowance
        )
    )

    # ========================================================
    # Immediate Zero-Balance Case
    # ========================================================

    if latest_entry.remainingAllowance <= 0:

        return ForecastResponse(
            depletion_expected_before_next_allowance=True,

            predicted_days_until_depletion=0,

            estimated_depletion_date=(
                philippine_today.isoformat()
            ),

            next_allowance_date=(
                next_allowance_date.isoformat()
            ),

            risk_level="CRITICAL",
        )

    # ========================================================
    # STAGE 1
    # Depletion Classification
    # ========================================================

    try:
        classifier_output = classifier.predict(
            model_input,
            verbose=0,
        )

    except Exception as exc:
        raise RuntimeError(
            "Depletion classifier "
            f"prediction failed: {exc}"
        ) from exc

    depletion_probability = float(
        classifier_output.flatten()[0]
    )

    if not np.isfinite(
        depletion_probability
    ):
        raise RuntimeError(
            "Depletion classifier returned "
            "a non-finite prediction."
        )

    depletion_probability = float(
        np.clip(
            depletion_probability,
            0.0,
            1.0,
        )
    )

    depletion_expected = (
        depletion_probability
        >= DEPLETION_THRESHOLD
    )

    # ========================================================
    # STAGE 1 says NO
    # ========================================================

    if not depletion_expected:

        return ForecastResponse(
            depletion_expected_before_next_allowance=False,

            predicted_days_until_depletion=None,

            estimated_depletion_date=None,

            next_allowance_date=(
                next_allowance_date.isoformat()
            ),

            risk_level="LOW",
        )

    # ========================================================
    # STAGE 2
    # Predict Days Until Depletion
    # ========================================================

    try:
        regressor_output = regressor.predict(
            model_input,
            verbose=0,
        )

    except Exception as exc:
        raise RuntimeError(
            "Depletion-day regressor "
            f"prediction failed: {exc}"
        ) from exc

    predicted_value = float(
        regressor_output.flatten()[0]
    )

    if not np.isfinite(
        predicted_value
    ):
        raise RuntimeError(
            "Depletion-day regressor returned "
            "a non-finite prediction."
        )

    # ========================================================
    # Keep Prediction Inside Current Allowance Cycle
    # ========================================================

    predicted_value = float(
        np.clip(
            predicted_value,
            0.0,
            float(
                days_until_next_allowance
            ),
        )
    )

    # ========================================================
    # Convert to Whole Days
    # ========================================================

    predicted_days = int(
        np.round(
            predicted_value
        )
    )

    predicted_days = max(
        0,
        min(
            predicted_days,
            days_until_next_allowance,
        ),
    )

    # ========================================================
    # Estimated Depletion Date
    # ========================================================

    estimated_depletion_date = (
        philippine_today
        + timedelta(
            days=predicted_days
        )
    )

    # ========================================================
    # Risk Level
    # ========================================================

    risk_level = calculate_risk_level(
        depletion_expected=True,
        predicted_days=predicted_days,
    )

    # ========================================================
    # Final Response
    # ========================================================

    return ForecastResponse(
        depletion_expected_before_next_allowance=True,

        predicted_days_until_depletion=(
            predicted_days
        ),

        estimated_depletion_date=(
            estimated_depletion_date.isoformat()
        ),

        next_allowance_date=(
            next_allowance_date.isoformat()
        ),

        risk_level=risk_level,
    )