from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================
# Transaction Spending History
# ============================================================

class HistoryEntry(BaseModel):

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
# Forecast Request
# ============================================================

class ForecastRequest(BaseModel):

    recentHistory: List[HistoryEntry] = Field(
        ...,
        min_length=5,
        max_length=10,
    )


# ============================================================
# Forecast Response
# ============================================================

class ForecastResponse(BaseModel):

    depletion_expected_before_next_allowance: bool

    predicted_days_until_depletion: Optional[int] = None

    estimated_depletion_date: Optional[str] = None

    next_allowance_date: str

    risk_level: str


# ============================================================
# Forecast Health Response
# ============================================================

class ForecastHealthResponse(BaseModel):

    status: str

    classifier_exists: bool

    regressor_exists: bool

    scaler_exists: bool