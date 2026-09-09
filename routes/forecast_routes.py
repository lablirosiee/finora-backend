from fastapi import APIRouter, HTTPException, status

from config import MODEL_PATH, SCALER_PATH
from schemas.forecast_schemas import (
    ForecastHealthResponse,
    ForecastRequest,
    ForecastResponse,
)
from services.forecast_service import generate_forecast


router = APIRouter(
    prefix="/forecast",
    tags=["Allowance Forecasting"],
)


# ============================================================
# Forecast Health Check
# ============================================================

@router.get(
    "/health",
    response_model=ForecastHealthResponse,
    status_code=status.HTTP_200_OK,
)
def forecast_health_check() -> ForecastHealthResponse:
    """
    Checks whether the GRU model and scaler files
    are available to the backend.
    """

    return ForecastHealthResponse(
        status="ok",
        model_exists=MODEL_PATH.exists(),
        scaler_exists=SCALER_PATH.exists(),
    )


# ============================================================
# Allowance Forecast
# ============================================================

@router.post(
    "",
    response_model=ForecastResponse,
    status_code=status.HTTP_200_OK,
)
def forecast_allowance(
    request: ForecastRequest,
) -> ForecastResponse:
    """
    Generates an allowance depletion forecast
    using the trained Finora GRU model.

    Expected output:
    - predicted_days_until_depletion
    - estimated_depletion_date
    - risk_level
    """

    try:
        return generate_forecast(request)

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecast generation failed: {exc}",
        ) from exc