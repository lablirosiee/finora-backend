from pydantic import BaseModel, EmailStr, Field


class OtpEmailRequest(BaseModel):
    email: EmailStr

    otp: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
    )


class OtpEmailResponse(BaseModel):
    success: bool
    message: str