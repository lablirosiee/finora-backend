from __future__ import annotations

import pickle
import time

from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from tensorflow.keras.models import load_model

from config import (
    CLASSIFIER_MODEL_PATH,
    DEPLETION_THRESHOLD,
    FEATURE_COLUMNS,
    MASK_VALUE,
    MAX_SEQUENCE_LENGTH,
    MIN_DISTINCT_EXPENSE_DAYS,
    MIN_TRANSACTIONS,
    REGRESSOR_MODEL_PATH,
    SCALER_PATH,
)

from schemas.forecast_schemas import (
    ForecastRequest,
    ForecastResponse,
    HistoryEntry,
    SimulationRequest,
)


# ============================================================
# Finora V9 Forecast Service
# ============================================================

MODEL_VERSION = "V9"


# ============================================================
# Load V9 Models and Scaler
# ============================================================

def load_model_artifacts() -> Tuple[
    Any,
    Any,
    Any,
]:
    """
    Load the frozen Finora V9 classifier, regressor, and scaler.

    The function is normally called through get_artifacts(),
    which caches the loaded objects so that TensorFlow models
    are not reloaded for every forecast request.
    """

    print(
        "[FORECAST] Checking V9 model artifacts...",
        flush=True,
    )

    if not CLASSIFIER_MODEL_PATH.exists():
        raise FileNotFoundError(
            "V9 classifier model not found: "
            f"{CLASSIFIER_MODEL_PATH}"
        )

    if not REGRESSOR_MODEL_PATH.exists():
        raise FileNotFoundError(
            "V9 regressor model not found: "
            f"{REGRESSOR_MODEL_PATH}"
        )

    if not SCALER_PATH.exists():
        raise FileNotFoundError(
            "V9 scaler not found: "
            f"{SCALER_PATH}"
        )

    # ========================================================
    # Classifier
    # ========================================================

    classifier_start = time.perf_counter()

    print(
        "[FORECAST] Loading V9 classifier model...",
        flush=True,
    )

    classifier = load_model(
        str(CLASSIFIER_MODEL_PATH),
        compile=False,
    )

    print(
        "[FORECAST] V9 classifier loaded in "
        f"{time.perf_counter() - classifier_start:.2f}s",
        flush=True,
    )

    # ========================================================
    # Regressor
    # ========================================================

    regressor_start = time.perf_counter()

    print(
        "[FORECAST] Loading V9 regressor model...",
        flush=True,
    )

    regressor = load_model(
        str(REGRESSOR_MODEL_PATH),
        compile=False,
    )

    print(
        "[FORECAST] V9 regressor loaded in "
        f"{time.perf_counter() - regressor_start:.2f}s",
        flush=True,
    )

    # ========================================================
    # Scaler
    # ========================================================

    scaler_start = time.perf_counter()

    print(
        "[FORECAST] Loading V9 scaler...",
        flush=True,
    )

    with SCALER_PATH.open(
        "rb"
    ) as file:
        scaler = pickle.load(file)

    print(
        "[FORECAST] V9 scaler loaded in "
        f"{time.perf_counter() - scaler_start:.2f}s",
        flush=True,
    )

    return (
        classifier,
        regressor,
        scaler,
    )


# ============================================================
# Cached V9 Artifacts
# ============================================================

@lru_cache(maxsize=1)
def get_artifacts() -> Tuple[
    Any,
    Any,
    Any,
]:
    """
    Return cached Finora V9 model artifacts.
    """

    return load_model_artifacts()


# ============================================================
# Validate Transaction History
# ============================================================

def validate_history(
    request: ForecastRequest,
) -> None:

    history = request.recentHistory

    history_length = len(
        history
    )

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
            "V9 scaler feature count mismatch. "
            f"Scaler expects {scaler_feature_count}, "
            f"backend provides {len(FEATURE_COLUMNS)}."
        )

    scaler_feature_names = getattr(
        scaler,
        "feature_names_in_",
        None,
    )

    if scaler_feature_names is not None:

        actual_names = [
            str(name)
            for name in scaler_feature_names
        ]

        if actual_names != FEATURE_COLUMNS:
            raise RuntimeError(
                "V9 scaler feature order mismatch. "
                f"Scaler expects {actual_names}, "
                f"backend provides {FEATURE_COLUMNS}."
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
            f"{model_name} sequence length mismatch. "
            f"Model expects {expected_sequence_length}, "
            f"backend provides {MAX_SEQUENCE_LENGTH}."
        )

    if (
        expected_feature_count is not None
        and expected_feature_count
        != len(FEATURE_COLUMNS)
    ):
        raise RuntimeError(
            f"{model_name} feature count mismatch. "
            f"Model expects {expected_feature_count}, "
            f"backend provides {len(FEATURE_COLUMNS)}."
        )


# ============================================================
# Build V9 GRU Input Sequence
# ============================================================

def build_input_sequence(
    request: ForecastRequest,
    scaler,
) -> np.ndarray:

    validate_history(
        request
    )

    verify_scaler(
        scaler
    )

    # ========================================================
    # Raw V9 feature sequence
    # ========================================================

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

    if (
        raw_sequence.shape
        != expected_raw_shape
    ):
        raise RuntimeError(
            "Unexpected raw input shape: "
            f"{raw_sequence.shape}. "
            f"Expected: {expected_raw_shape}."
        )

    # ========================================================
    # Scale using exact V9 feature names/order
    # ========================================================

    try:

        raw_dataframe = pd.DataFrame(
            raw_sequence,
            columns=FEATURE_COLUMNS,
        )

        scaled_sequence = (
            scaler.transform(
                raw_dataframe
            )
            .astype(
                np.float32
            )
        )

    except Exception as exc:
        raise ValueError(
            "V9 scaler transform failed: "
            f"{exc}"
        ) from exc

    if (
        scaled_sequence.shape
        != expected_raw_shape
    ):
        raise RuntimeError(
            "Unexpected scaled input shape: "
            f"{scaled_sequence.shape}. "
            f"Expected: {expected_raw_shape}."
        )

    # ========================================================
    # Right-pad after scaling
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
    """
    Risk refers to the CURRENT allowance cycle.

    If Stage 1 predicts that the balance will survive until
    the next allowance, current-cycle risk is LOW even though
    Stage 2 can still provide a longer depletion horizon.
    """

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
# Generate V9 Forecast
# ============================================================

def generate_forecast(
    request: ForecastRequest,
) -> ForecastResponse:

    total_start = time.perf_counter()

    print(
        "[FORECAST] ========================================",
        flush=True,
    )

    print(
        "[FORECAST] Finora V9 forecast request received.",
        flush=True,
    )

    print(
        "[FORECAST] Transaction count: "
        f"{len(request.recentHistory)}",
        flush=True,
    )

    # ========================================================
    # Retrieve Cached V9 Artifacts
    # ========================================================

    artifact_start = time.perf_counter()

    print(
        "[FORECAST] Retrieving V9 model artifacts...",
        flush=True,
    )

    (
        classifier,
        regressor,
        scaler,
    ) = get_artifacts()

    print(
        "[FORECAST] V9 artifacts ready in "
        f"{time.perf_counter() - artifact_start:.2f}s",
        flush=True,
    )

    # ========================================================
    # Verify Models
    # ========================================================

    verify_start = time.perf_counter()

    verify_model_shape(
        classifier,
        "V9 classifier",
    )

    verify_model_shape(
        regressor,
        "V9 regressor",
    )

    print(
        "[FORECAST] V9 model verification completed in "
        f"{time.perf_counter() - verify_start:.2f}s",
        flush=True,
    )

    # ========================================================
    # Build Input
    # ========================================================

    input_start = time.perf_counter()

    padded_sequence = build_input_sequence(
        request,
        scaler,
    )

    model_input = padded_sequence.reshape(
        1,
        MAX_SEQUENCE_LENGTH,
        len(FEATURE_COLUMNS),
    )

    print(
        "[FORECAST] Input sequence built in "
        f"{time.perf_counter() - input_start:.2f}s",
        flush=True,
    )

    print(
        "[FORECAST] V9 GRU input shape: "
        f"{model_input.shape}",
        flush=True,
    )

    # ========================================================
    # Latest Financial State
    # ========================================================

    latest_entry = (
        request.recentHistory[-1]
    )

    days_until_next_allowance = int(
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

    if (
        latest_entry.remainingAllowance
        <= 0
    ):

        print(
            "[FORECAST] Remaining allowance is zero.",
            flush=True,
        )

        print(
            "[FORECAST] Depletion expected: True",
            flush=True,
        )

        print(
            "[FORECAST] Predicted days until depletion: 0",
            flush=True,
        )

        print(
            "[FORECAST] Risk level: CRITICAL",
            flush=True,
        )

        print(
            "[FORECAST] Total processing time: "
            f"{time.perf_counter() - total_start:.2f}s",
            flush=True,
        )

        print(
            "[FORECAST] ========================================",
            flush=True,
        )

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
    # V9 Depletion Classifier
    # ========================================================

    classifier_start = time.perf_counter()

    print(
        "[FORECAST] Starting V9 Stage 1 "
        "classifier prediction...",
        flush=True,
    )

    try:

        classifier_output = classifier.predict(
            model_input,
            verbose=0,
        )

    except Exception as exc:
        raise RuntimeError(
            "V9 depletion classifier prediction failed: "
            f"{exc}"
        ) from exc

    classifier_duration = (
        time.perf_counter()
        - classifier_start
    )

    depletion_probability = float(
        np.asarray(
            classifier_output
        ).reshape(-1)[0]
    )

    if not np.isfinite(
        depletion_probability
    ):
        raise RuntimeError(
            "V9 depletion classifier returned "
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

    print(
        "[FORECAST] Stage 1 completed in "
        f"{classifier_duration:.2f}s",
        flush=True,
    )

    print(
        "[FORECAST] Depletion probability: "
        f"{depletion_probability:.6f}",
        flush=True,
    )

    print(
        "[FORECAST] V9 depletion threshold: "
        f"{DEPLETION_THRESHOLD:.4f}",
        flush=True,
    )

    print(
        "[FORECAST] Depletion expected before "
        "next allowance: "
        f"{depletion_expected}",
        flush=True,
    )

    # ========================================================
    # STAGE 2
    # V9 Depletion-Day Regressor
    #
    # IMPORTANT:
    # V9 Stage 2 runs for BOTH Stage 1 outcomes.
    # ========================================================

    regressor_start = time.perf_counter()

    print(
        "[FORECAST] Starting V9 Stage 2 "
        "regressor prediction...",
        flush=True,
    )

    try:

        regressor_output = regressor.predict(
            model_input,
            verbose=0,
        )

    except Exception as exc:
        raise RuntimeError(
            "V9 depletion-day regressor prediction failed: "
            f"{exc}"
        ) from exc

    regressor_duration = (
        time.perf_counter()
        - regressor_start
    )

    predicted_value = float(
        np.asarray(
            regressor_output
        ).reshape(-1)[0]
    )

    if not np.isfinite(
        predicted_value
    ):
        raise RuntimeError(
            "V9 depletion-day regressor returned "
            "a non-finite prediction."
        )

    # ========================================================
    # V9 does NOT clip Stage 2 to next allowance
    # ========================================================

    predicted_value = max(
        0.0,
        predicted_value,
    )

    print(
        "[FORECAST] Stage 2 completed in "
        f"{regressor_duration:.2f}s",
        flush=True,
    )

    print(
        "[FORECAST] Raw predicted depletion days: "
        f"{predicted_value:.6f}",
        flush=True,
    )

    # ========================================================
    # Convert Prediction to Whole Days
    # ========================================================

    predicted_days = max(
        0,
        int(
            np.round(
                predicted_value
            )
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
    # Current-Cycle Risk
    # ========================================================

    risk_level = calculate_risk_level(
        depletion_expected=depletion_expected,
        predicted_days=predicted_days,
    )

    # ========================================================
    # Logical Diagnostic
    # ========================================================

    stage2_before_next_allowance = (
        predicted_value
        <= float(
            days_until_next_allowance
        )
    )

    stage_consistent = (
        depletion_expected
        == stage2_before_next_allowance
    )

    print(
        "[FORECAST] Predicted days until depletion: "
        f"{predicted_days}",
        flush=True,
    )

    print(
        "[FORECAST] Estimated depletion date: "
        f"{estimated_depletion_date.isoformat()}",
        flush=True,
    )

    print(
        "[FORECAST] Next allowance date: "
        f"{next_allowance_date.isoformat()}",
        flush=True,
    )

    print(
        "[FORECAST] Risk level: "
        f"{risk_level}",
        flush=True,
    )

    print(
        "[FORECAST] Stage 1 / Stage 2 consistent: "
        f"{stage_consistent}",
        flush=True,
    )

    if not stage_consistent:
        print(
            "[FORECAST] WARNING: V9 stages produced "
            "different boundary decisions. "
            "Returning the model outputs without "
            "silently modifying either prediction.",
            flush=True,
        )

    print(
        "[FORECAST] Total processing time: "
        f"{time.perf_counter() - total_start:.2f}s",
        flush=True,
    )

    print(
        "[FORECAST] ========================================",
        flush=True,
    )

    # ========================================================
    # Final V9 Response
    # ========================================================

    return ForecastResponse(
        depletion_expected_before_next_allowance=(
            depletion_expected
        ),
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


# ============================================================
# Generate What-If Simulation Forecast
# ============================================================

def generate_simulation_forecast(
    request: SimulationRequest,
) -> ForecastResponse:
    """
    Generate a hypothetical allowance forecast using the
    SAME frozen Finora V9 two-stage GRU pipeline.

    The user's real transaction history remains unchanged.
    A hypothetical transaction exists only in memory.

    This function does NOT:
    - save an expense
    - update Room
    - update Firestore
    - modify the user's allowance
    - overwrite the user's real forecast
    """

    print(
        "[SIMULATION] ========================================",
        flush=True,
    )

    print(
        "[SIMULATION] V9 What-If simulation requested.",
        flush=True,
    )

    # ========================================================
    # Existing History
    # ========================================================

    history = request.recentHistory

    if len(history) < MIN_TRANSACTIONS:
        raise ValueError(
            "Simulation requires at least "
            f"{MIN_TRANSACTIONS} existing expense transactions."
        )

    if len(history) > MAX_SEQUENCE_LENGTH:
        raise ValueError(
            "Simulation accepts at most "
            f"{MAX_SEQUENCE_LENGTH} recent transactions."
        )

    # ========================================================
    # Planned Expense
    # ========================================================

    planned_amount = float(
        request.plannedExpenseAmount
    )

    if planned_amount <= 0:
        raise ValueError(
            "Planned expense amount must be greater than zero."
        )

    # ========================================================
    # Category
    # ========================================================

    normalized_category = (
        request.category
        .strip()
        .lower()
        .replace("_", "-")
        .replace(" ", "-")
    )

    if (
        normalized_category
        == "essential"
    ):
        is_essential = True

    elif normalized_category in {
        "non-essential",
        "nonessential",
    }:
        is_essential = False

    else:
        raise ValueError(
            "Simulation category must be either "
            "'Essential' or 'Non-Essential'."
        )

    # ========================================================
    # Latest Actual State
    # ========================================================

    latest_entry = history[-1]

    allowance_amount = float(
        latest_entry.allowanceAmount
    )

    current_remaining = float(
        latest_entry.remainingAllowance
    )

    if allowance_amount <= 0:
        raise ValueError(
            "Allowance amount must be greater than zero."
        )

    # ========================================================
    # Hypothetical State
    # ========================================================

    hypothetical_remaining = max(
        0.0,
        current_remaining
        - planned_amount,
    )

    hypothetical_essential = (
        planned_amount
        if is_essential
        else 0.0
    )

    hypothetical_non_essential = (
        planned_amount
        if not is_essential
        else 0.0
    )

    hypothetical_percentage_used = (
        (
            allowance_amount
            - hypothetical_remaining
        )
        / allowance_amount
    ) * 100.0

    hypothetical_percentage_used = max(
        0.0,
        min(
            hypothetical_percentage_used,
            100.0,
        ),
    )

    # ========================================================
    # Simulation Date
    # ========================================================

    simulation_date = datetime.now(
        ZoneInfo("Asia/Manila")
    ).date()

    if (
        latest_entry.date
        > simulation_date
    ):
        raise ValueError(
            "The latest transaction date cannot be "
            "later than the simulation date."
        )

    # ========================================================
    # Temporal Features
    # ========================================================

    days_since_previous = (
        simulation_date
        - latest_entry.date
    ).days

    hypothetical_days_until_next_allowance = max(
        0,
        (
            latest_entry.daysUntilNextAllowance
            - days_since_previous
        ),
    )

    # ========================================================
    # Hypothetical Transaction
    # ========================================================

    hypothetical_entry = HistoryEntry(
        date=simulation_date,

        transactionAmount=(
            planned_amount
        ),

        remainingAllowance=(
            hypothetical_remaining
        ),

        essentialExpense=(
            hypothetical_essential
        ),

        nonEssentialExpense=(
            hypothetical_non_essential
        ),

        daysSincePreviousExpense=(
            days_since_previous
        ),

        daysUntilNextAllowance=(
            hypothetical_days_until_next_allowance
        ),

        allowanceAmount=(
            allowance_amount
        ),

        percentageAllowanceUsed=(
            hypothetical_percentage_used
        ),
    )

    # ========================================================
    # Temporary History
    # ========================================================

    simulated_history = list(
        history
    )

    simulated_history.append(
        hypothetical_entry
    )

    if (
        len(simulated_history)
        > MAX_SEQUENCE_LENGTH
    ):
        simulated_history = (
            simulated_history[
                -MAX_SEQUENCE_LENGTH:
            ]
        )

    simulated_request = ForecastRequest(
        recentHistory=simulated_history
    )

    # ========================================================
    # Debugging
    # ========================================================

    print(
        "[SIMULATION] Planned expense: "
        f"{planned_amount:.2f}",
        flush=True,
    )

    print(
        "[SIMULATION] Category: "
        f"{request.category}",
        flush=True,
    )

    print(
        "[SIMULATION] Current remaining: "
        f"{current_remaining:.2f}",
        flush=True,
    )

    print(
        "[SIMULATION] Projected remaining: "
        f"{hypothetical_remaining:.2f}",
        flush=True,
    )

    print(
        "[SIMULATION] Allowance used after simulation: "
        f"{hypothetical_percentage_used:.2f}%",
        flush=True,
    )

    print(
        "[SIMULATION] Days until next allowance: "
        f"{hypothetical_days_until_next_allowance}",
        flush=True,
    )

    print(
        "[SIMULATION] V9 GRU transaction count: "
        f"{len(simulated_history)}",
        flush=True,
    )

    # ========================================================
    # SAME V9 PRODUCTION PIPELINE
    # ========================================================

    result = generate_forecast(
        simulated_request
    )

    print(
        "[SIMULATION] Result: "
        f"risk={result.risk_level}, "
        f"depletionExpected="
        f"{result.depletion_expected_before_next_allowance}, "
        f"days="
        f"{result.predicted_days_until_depletion}",
        flush=True,
    )

    print(
        "[SIMULATION] ========================================",
        flush=True,
    )

    return result