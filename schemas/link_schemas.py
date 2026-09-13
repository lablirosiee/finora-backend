from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


# ============================================================
# Link Notification Request
# ============================================================

class LinkNotificationRequest(BaseModel):
    """
    Request used after a legitimate link-request status change.

    The client supplies only the request ID and event type.

    The backend reads the real Provider and Student IDs from
    Firestore instead of trusting recipient IDs from Android.
    """

    requestId: str = Field(
        ...,
        min_length=1,
    )

    eventType: str = Field(
        ...,
        min_length=1,
    )

    @field_validator(
        "requestId",
        "eventType",
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
# Link Notification Response
# ============================================================

class LinkNotificationResponse(BaseModel):

    success: bool

    notificationId: str | None = None

    skipped: bool = False

    message: str


# ============================================================
# Unlink Request
# ============================================================

class UnlinkAccountsRequest(BaseModel):
    """
    Request used to securely unlink a Provider and Student.

    The backend verifies that the authenticated user is one of
    the participants before deleting the linked account.
    """

    providerId: str = Field(
        ...,
        min_length=1,
    )

    studentId: str = Field(
        ...,
        min_length=1,
    )

    @field_validator(
        "providerId",
        "studentId",
        mode="before",
    )
    @classmethod
    def strip_unlink_fields(
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
# Unlink Response
# ============================================================

class UnlinkAccountsResponse(BaseModel):

    success: bool

    message: str