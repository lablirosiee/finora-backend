from fastapi import FastAPI

from routes.otp_routes import router as otp_router
from routes.fcm_routes import router as fcm_router
from routes.profile_routes import router as profile_router
from routes.auth_routes import router as auth_router


app = FastAPI(
    title="Finora API",
    description="Finora backend API for email OTP delivery.",
    version="1.0.0",
)


app.include_router(otp_router)
app.include_router(fcm_router)
app.include_router(profile_router)
app.include_router(auth_router)

@app.get("/")
def root():
    return {
        "message": "Finora API is running.",
        "documentation": "/docs",
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "Finora OTP API",
    }