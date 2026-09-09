import pickle

from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Tuple
from zoneinfo import ZoneInfo

import numpy as np
from tensorflow.keras.models import load_model

from config import (
    MODEL_PATH,
    SCALER_PATH,
)

from schemas.forecast_schemas import (
    ForecastRequest,
    ForecastResponse,
)


# ============================================================
# GRU Configuration
# ============================================================

SEQUENCE_LENGTH = 30

FEATURE_COLUMNS = [
    "dailyExpense",
    "remainingAllowance",
    "essentialExpense",
    "nonEssentialExpense",
    "daysUntilNextAllowance",
    "allowanceAmount",
]


# ============================================================
# Load GRU Model and Scaler
# ============================================================

def load_model_and_scaler() -> Tuple[Any, Any]:

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found: {MODEL_PATH}"
        )

    if not SCALER_PATH.exists():
        raise FileNotFoundError(
            f"Scaler not found: {SCALER_PATH}"
        )

    model = load_model(
        str(MODEL_PATH),
        compile=False,
    )

    with SCALER_PATH.open("rb") as file:
        scaler = pickle.load(file)

    return model, scaler


# ============================================================
# Cache Model and Scaler
# ============================================================

@lru_cache(maxsize=1)
def get_artifacts() -> Tuple[Any, Any]:
    return load_model_and_scaler()


# ============================================================
# Validate History
# ============================================================

def validate_history(
    request: ForecastRequest,
) -> None:

    history_length = len(
        request.recentHistory
    )

    if history_length != SEQUENCE_LENGTH:
        raise ValueError(
            "recentHistory must contain exactly "
            f"{SEQUENCE_LENGTH} entries. "
            f"Received: {history_length}."
        )


# ============================================================
# Build GRU Input Sequence
# ============================================================

def build_input_sequence(
    request: ForecastRequest,
    scaler,
) -> np.ndarray:

    validate_history(request)

    raw_sequence = np.asarray(
        [
            [
                entry.dailyExpense,
                entry.remainingAllowance,
                entry.essentialExpense,
                entry.nonEssentialExpense,
                entry.daysUntilNextAllowance,
                entry.allowanceAmount,
            ]
            for entry in request.recentHistory
        ],
        dtype=np.float32,
    )

    expected_shape = (
        SEQUENCE_LENGTH,
        len(FEATURE_COLUMNS),
    )

    if raw_sequence.shape != expected_shape:
        raise RuntimeError(
            "Unexpected raw input shape: "
            f"{raw_sequence.shape}. "
            f"Expected: {expected_shape}."
        )

    # ========================================================
    # Verify scaler configuration
    # ========================================================

    scaler_feature_count = getattr(
        scaler,
        "n_features_in_",
        None,
    )

    if (
        scaler_feature_count is not None
        and scaler_feature_count != len(FEATURE_COLUMNS)
    ):
        raise RuntimeError(
            "Scaler feature count mismatch. "
            f"Scaler expects {scaler_feature_count}, "
            f"backend provides {len(FEATURE_COLUMNS)}."
        )

    # ========================================================
    # Scale Input
    # ========================================================

    try:
        scaled_sequence = scaler.transform(
            raw_sequence
        )

    except Exception as exc:
        raise ValueError(
            f"Scaler transform failed: {exc}"
        ) from exc

    if scaled_sequence.shape != expected_shape:
        raise RuntimeError(
            "Unexpected scaled input shape: "
            f"{scaled_sequence.shape}. "
            f"Expected: {expected_shape}."
        )

    return scaled_sequence


# ============================================================
# Risk Level
# ============================================================

def calculate_risk_level(
    predicted_days: int,
    current_remaining: float,
    current_allowance: float,
) -> str:

    if predicted_days <= 3:
        return "CRITICAL"

    if predicted_days <= 7:
        return "HIGH"

    if predicted_days <= 14:
        return "MODERATE"

    if current_allowance <= 0:
        return "UNKNOWN"

    allowance_ratio = (
        current_remaining
        / current_allowance
    )

    if allowance_ratio > 0.50:
        return "LOW"

    if allowance_ratio > 0.25:
        return "MODERATE"

    if allowance_ratio > 0.10:
        return "HIGH"

    return "CRITICAL"


# ============================================================
# Generate Forecast
# ============================================================

def generate_forecast(
    request: ForecastRequest,
) -> ForecastResponse:

    model, scaler = get_artifacts()

    scaled_sequence = build_input_sequence(
        request,
        scaler,
    )

    # ========================================================
    # GRU Input Shape
    #
    # Expected:
    # (batch, sequence, features)
    #
    # Current Finora model:
    # (1, 30, 6)
    # ========================================================

    model_input = scaled_sequence.reshape(
        1,
        SEQUENCE_LENGTH,
        len(FEATURE_COLUMNS),
    )

    # ========================================================
    # Verify Model Shape
    # ========================================================

    model_shape = model.input_shape

    if len(model_shape) != 3:
        raise RuntimeError(
            "Unexpected GRU model input shape: "
            f"{model_shape}"
        )

    expected_sequence_length = (
        model_shape[1]
    )

    expected_feature_count = (
        model_shape[2]
    )

    if (
        expected_sequence_length is not None
        and expected_sequence_length != SEQUENCE_LENGTH
    ):
        raise RuntimeError(
            "GRU sequence length mismatch. "
            f"Model expects {expected_sequence_length}, "
            f"backend provides {SEQUENCE_LENGTH}."
        )

    if (
        expected_feature_count is not None
        and expected_feature_count != len(FEATURE_COLUMNS)
    ):
        raise RuntimeError(
            "GRU feature count mismatch. "
            f"Model expects {expected_feature_count}, "
            f"backend provides {len(FEATURE_COLUMNS)}."
        )

    # ========================================================
    # Prediction
    # ========================================================

    try:
        prediction = model.predict(
            model_input,
            verbose=0,
        )

    except Exception as exc:
        raise RuntimeError(
            f"GRU prediction failed: {exc}"
        ) from exc

    predicted_value = float(
        prediction.flatten()[0]
    )

    if not np.isfinite(
        predicted_value
    ):
        raise RuntimeError(
            "GRU returned a non-finite prediction."
        )

    # ========================================================
    # Convert Prediction to Days
    # ========================================================

    predicted_days = int(
        np.clip(
            np.round(predicted_value),
            1,
            60,
        )
    )

    # ========================================================
    # Estimated Depletion Date
    # ========================================================

    philippine_today = datetime.now(
        ZoneInfo("Asia/Manila")
    ).date()

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
        predicted_days=predicted_days,
        current_remaining=(
            request.currentRemainingAllowance
        ),
        current_allowance=(
            request.currentAllowanceAmount
        ),
    )

    # ========================================================
    # Response
    # ========================================================

    return ForecastResponse(
        predicted_days_until_depletion=(
            predicted_days
        ),
        estimated_depletion_date=(
            estimated_depletion_date.isoformat()
        ),
        risk_level=risk_level,
    )