from pydantic import BaseModel, Field, field_validator


# ============================================================
# FCM Test Request
# ============================================================

class FcmSendRequest(BaseModel):
    """
    Request model used by the FCM test endpoint.

    This endpoint is for testing push delivery only.
    Production notifications should use the notification
    service instead.
    """

    userId: str = Field(
        ...,
        min_length=1,
    )

    type: str = Field(
        ...,
        min_length=1,
    )

    title: str = Field(
        ...,
        min_length=1,
    )

    message: str = Field(
        ...,
        min_length=1,
    )

    notificationId: str = ""
    studentId: str = ""


    @field_validator(
        "userId",
        "type",
        "title",
        "message",
        "notificationId",
        "studentId",
        mode="before",
    )
    @classmethod
    def strip_string_fields(
        cls,
        value,
    ):
        """
        Remove accidental leading/trailing spaces from
        incoming string values.
        """

        if isinstance(value, str):
            return value.strip()

        return value


# ============================================================
# FCM Test Response
# ============================================================

class FcmSendResponse(BaseModel):
    success: bool

    messageId: str