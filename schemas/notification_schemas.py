from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


# ============================================================
# Production Notification Event Request
# ============================================================

class NotificationEventRequest(BaseModel):
    """
    Request sent by the authenticated Android app when the
    current Finora user experiences an own-finance event.

    The backend determines:
        - recipient
        - title
        - message
        - canonical notification type

    Android must not choose an arbitrary notification recipient.
    """

    eventType: str = Field(
        ...,
        min_length=1,
    )

    studentId: str = Field(
        default="",
    )

    @field_validator(
        "eventType",
        "studentId",
        mode="before",
    )
    @classmethod
    def strip_string_fields(
        cls,
        value,
    ):

        if isinstance(
            value,
            str,
        ):

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