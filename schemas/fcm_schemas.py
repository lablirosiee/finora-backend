from pydantic import BaseModel, Field


class FcmSendRequest(BaseModel):
    userId: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)

    notificationId: str = ""
    studentId: str = ""


class FcmSendResponse(BaseModel):
    success: bool
    messageId: str