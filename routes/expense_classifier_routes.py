from fastapi import APIRouter, HTTPException

from schemas.expense_classifier_schemas import (
    ExpenseClassificationRequest,
    ExpenseClassificationResponse,
)

from services.expense_classifier_service import (
    classify_expense,
)


router = APIRouter(
    prefix="/expense",
    tags=["Expense Classification"],
)


# ============================================================
# CLASSIFY EXPENSE
# ============================================================

@router.post(
    "/classify",
    response_model=ExpenseClassificationResponse,
)
async def classify_expense_endpoint(
    request: ExpenseClassificationRequest,
):

    try:

        result = classify_expense(
            product_name=request.productName,
            note=request.note,
            ocr_text=request.ocrText,
        )

        return result

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:

        print(
            f"Expense classification error: {error}"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to classify expense."
            ),
        )