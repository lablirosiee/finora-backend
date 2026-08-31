from pydantic import BaseModel, Field, field_validator


# ============================================================
# Production Notification Event Request
# ============================================================

class NotificationEventRequest(BaseModel):
    """
    Request sent by the authenticated Android app when a
    legitimate Finora event needs a notification.

    The backend will determine the final title, message,
    notification type, and recipient rules.
    """

    eventType: str = Field(
        ...,
        min_length=1,
    )

    targetUserId: str = Field(
        default="",
    )

    studentId: str = Field(
        default="",
    )


    @field_validator(
        "eventType",
        "targetUserId",
        "studentId",
        mode="before",
    )
    @classmethod
    def strip_string_fields(
        cls,
        value,
    ):
        if isinstance(value, str):
            return value.strip()

        return value


# ============================================================
# Production Notification Event Response
# ============================================================

class NotificationEventResponse(BaseModel):
    success: bool
    notificationId: str | None = None
    skipped: bool = False
    message: str