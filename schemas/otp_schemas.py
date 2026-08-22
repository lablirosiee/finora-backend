from pydantic import BaseModel, EmailStr, Field


class OtpRequest(BaseModel):
    email: EmailStr
    purpose: str = Field(..., description="Allowed: 'signup', 'password_reset'")


class OtpRequestResponse(BaseModel):
    success: bool
    message: str


class OtpVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    purpose: str = Field(..., description="Allowed: 'signup', 'password_reset'")


class OtpVerifyResponse(BaseModel):
    success: bool
    verificationToken: str
