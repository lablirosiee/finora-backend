from fastapi import FastAPI

from routes.otp_routes import router as otp_router
from routes.fcm_routes import router as fcm_router
from routes.profile_routes import router as profile_router
from routes.auth_routes import router as auth_router
from routes.notification_routes import router as notification_router


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title="Finora API",
    description=(
        "Backend API for Finora authentication, OTP, "
        "profile services, notifications, FCM, and "
        "forecasting."
    ),
    version="1.0.0",
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


# ============================================================
# Root
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Finora API is running.",
        "documentation": "/docs",
    }


# ============================================================
# Health Check
# ============================================================

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "Finora API",
    }