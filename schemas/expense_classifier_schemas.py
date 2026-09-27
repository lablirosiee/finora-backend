from typing import List

from pydantic import BaseModel, Field


# ============================================================
# REQUEST
# ============================================================

class ExpenseClassificationRequest(BaseModel):

    productName: str = Field(
        default="",
        max_length=200,
    )

    note: str = Field(
        default="",
        max_length=500,
    )

    ocrText: str = Field(
        default="",
        max_length=5000,
    )


# ============================================================
# ALTERNATIVE PREDICTION
# ============================================================

class ExpensePredictionAlternative(BaseModel):

    category: str

    subcategory: str

    confidence: float


# ============================================================
# RESPONSE
# ============================================================

class ExpenseClassificationResponse(BaseModel):

    category: str

    subcategory: str

    confidence: float

    source: str

    inputText: str

    alternatives: List[
        ExpensePredictionAlternative
    ]