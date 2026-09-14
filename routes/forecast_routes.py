from fastapi import (
    APIRouter,
    HTTPException,
    status,
)

from config import (
    CLASSIFIER_MODEL_PATH,
    REGRESSOR_MODEL_PATH,
    SCALER_PATH,
)

from schemas.forecast_schemas import (
    ForecastHealthResponse,
    ForecastRequest,
    ForecastResponse,
)

from services.forecast_service import (
    generate_forecast,
)


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
    Checks whether both Finora V8 GRU models
    and the scaler are available.
    """

    classifier_exists = (
        CLASSIFIER_MODEL_PATH.exists()
    )

    regressor_exists = (
        REGRESSOR_MODEL_PATH.exists()
    )

    scaler_exists = (
        SCALER_PATH.exists()
    )

    all_available = (
        classifier_exists
        and regressor_exists
        and scaler_exists
    )

    return ForecastHealthResponse(
        status=(
            "ok"
            if all_available
            else "unavailable"
        ),

        classifier_exists=(
            classifier_exists
        ),

        regressor_exists=(
            regressor_exists
        ),

        scaler_exists=scaler_exists,
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
    Generates Finora's two-stage allowance forecast.

    Stage 1:
    Predict whether the current allowance is
    expected to deplete before the next allowance.

    Stage 2:
    If depletion is expected, predict the number
    of days until depletion.

    Eligibility:
    - 5 to 10 recent transactions
    - at least 3 distinct expense days
    """

    try:
        return generate_forecast(
            request
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Forecast generation failed: "
                f"{exc}"
            ),
        ) from exc