from typing import List

from pydantic import BaseModel, Field


# ============================================================
# Daily Spending History
# ============================================================

class HistoryEntry(BaseModel):
    dailyExpense: float = Field(
        ...,
        ge=0,
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

    daysUntilNextAllowance: int = Field(
        ...,
        ge=0,
    )

    allowanceAmount: float = Field(
        ...,
        gt=0,
    )


# ============================================================
# Forecast Request
# ============================================================

class ForecastRequest(BaseModel):
    recentHistory: List[HistoryEntry]

    currentRemainingAllowance: float = Field(
        ...,
        ge=0,
    )

    currentAllowanceAmount: float = Field(
        ...,
        gt=0,
    )


# ============================================================
# Forecast Response
# ============================================================

class ForecastResponse(BaseModel):
    predicted_days_until_depletion: int

    estimated_depletion_date: str

    risk_level: str


# ============================================================
# Forecast Health Response
# ============================================================

class ForecastHealthResponse(BaseModel):
    status: str

    model_exists: bool

    scaler_exists: bool