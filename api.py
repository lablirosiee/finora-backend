from fastapi import FastAPI

from routes.otp_routes import router as otp_router
from routes.fcm_routes import router as fcm_router
from routes.profile_routes import router as profile_router
from routes.auth_routes import router as auth_router
from routes.notification_routes import router as notification_router
from routes.forecast_routes import router as forecast_router
from routes.link_routes import router as link_router
from routes.expense_classifier_routes import router as expense_classifier_router


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title="Finora API",
    description=(
        "Backend API for Finora authentication, OTP, "
        "profile services, notifications, FCM, linking, "
        "two-stage GRU allowance forecasting, and "
        "AI-assisted expense classification."
    ),
    version="2.1.0",
)


# ============================================================
# Routers
# ============================================================

app.include_router(
    otp_router
)

app.include_router(
    auth_router
)

app.include_router(
    profile_router
)

app.include_router(
    fcm_router
)

app.include_router(
    notification_router
)

app.include_router(
    forecast_router
)

app.include_router(
    link_router
)

app.include_router(
    expense_classifier_router
)


# ============================================================
# Root
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Finora API is running.",
        "version": "2.1.0",
        "documentation": "/docs",
        "features": {
            "expenseClassification": True,
            "allowanceForecasting": True,
            "notifications": True,
            "linking": True,
        },
    }


# ============================================================
# Health Check
# ============================================================

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "Finora API",
        "version": "2.1.0",
    }