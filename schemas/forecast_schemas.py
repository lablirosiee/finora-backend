from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# Transaction Spending History
# ============================================================

class HistoryEntry(BaseModel):
    """
    Represents one transaction entry used by the
    Finora V8 Two-Stage GRU forecasting model.
    """

    date: date

    transactionAmount: float = Field(
        ...,
        gt=0,
    )

    remainingAllowance: float = Field(
        ...,
        ge=0,
    )

    essentialExpense: float = Field(
        ...,
        ge=0,
    )

    nonEssentialExpense: float = Field(
        ...,
        ge=0,
    )

    daysSincePreviousExpense: int = Field(
        ...,
        ge=0,
    )

    daysUntilNextAllowance: int = Field(
        ...,
        ge=0,
    )

    allowanceAmount: float = Field(
        ...,
        gt=0,
    )

    percentageAllowanceUsed: float = Field(
        ...,
        ge=0,
    )


# ============================================================
# Real Forecast Request
# ============================================================

class ForecastRequest(BaseModel):
    """
    Request used for the user's real allowance forecast.

    The V8 GRU requires:
    - at least 5 recent transactions
    - at most 10 recent transactions

    The transaction history must contain actual
    user expense data only.
    """

    recentHistory: List[HistoryEntry] = Field(
        ...,
        min_length=5,
        max_length=10,
    )


# ============================================================
# What-If Simulation Request
# ============================================================

class SimulationRequest(BaseModel):
    """
    Request used for Finora's What-If Simulation.

    recentHistory:
        The user's actual recent transaction history.

    plannedExpenseAmount:
        The hypothetical expense amount entered
        by the user.

    category:
        The hypothetical expense type.
        Must be either:
        - Essential
        - Non-Essential

    The backend uses these values to construct a
    hypothetical transaction in memory before
    running the same V8 Two-Stage GRU.

    The hypothetical transaction is never persisted
    to Firestore, Room, or the user's actual
    financial records.
    """

    recentHistory: List[HistoryEntry] = Field(
        ...,
        min_length=5,
        max_length=10,
    )

    plannedExpenseAmount: float = Field(
        ...,
        gt=0,
    )

    category: Literal[
        "Essential",
        "Non-Essential",
    ]


# ============================================================
# Forecast Response
# ============================================================

class ForecastResponse(BaseModel):
    """
    Response returned by both the real forecast
    and What-If simulation endpoints.
    """

    depletion_expected_before_next_allowance: bool

    predicted_days_until_depletion: Optional[int] = None

    estimated_depletion_date: Optional[str] = None

    next_allowance_date: str

    risk_level: str


# ============================================================
# Forecast Health Response
# ============================================================

class ForecastHealthResponse(BaseModel):
    """
    Reports whether the forecasting model files
    required by the backend are available.
    """

    status: str

    classifier_exists: bool

    regressor_exists: bool

    scaler_exists: bool