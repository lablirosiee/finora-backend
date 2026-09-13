import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from schemas.notification_schemas import (
    NotificationEventRequest,
    NotificationEventResponse,
)

from services.auth_service import (
    AuthenticatedUser,
    get_current_user,
)

from services.notification_service import (
    create_notification_if_not_recent,
)


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Router
# ============================================================

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


# ============================================================
# Supported Own-Finance Events
#
# IMPORTANT:
# These events apply to BOTH Student and Provider because both
# roles can independently manage their own finances.
# ============================================================

EVENT_ALLOWANCE_LOW = "ALLOWANCE_LOW"

EVENT_UNUSUAL_SPENDING = "UNUSUAL_SPENDING"

EVENT_FINANCIAL_RISK = "FINANCIAL_RISK"

EVENT_BUDGET_EXCEEDED = "BUDGET_EXCEEDED"

EVENT_FORECAST_UPDATE = "FORECAST_UPDATE"


SUPPORTED_OWN_FINANCE_EVENTS = {
    EVENT_ALLOWANCE_LOW,
    EVENT_UNUSUAL_SPENDING,
    EVENT_FINANCIAL_RISK,
    EVENT_BUDGET_EXCEEDED,
    EVENT_FORECAST_UPDATE,
}


# ============================================================
# Event Normalization
# ============================================================

def normalize_event_type(
    event_type: str,
) -> str:
    """
    Normalize an Android notification event into Finora's
    canonical uppercase format.
    """

    return (
        str(
            event_type or ""
        )
        .strip()
        .upper()
    )


# ============================================================
# Production Own-Finance Notification Endpoint
# ============================================================

@router.post(
    "/event",
    response_model=NotificationEventResponse,
    status_code=status.HTTP_200_OK,
)
def trigger_notification_event(
    request: NotificationEventRequest,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
) -> NotificationEventResponse:
    """
    Handle an authenticated Finora user's own financial
    notification event.

    Both Student and Provider may trigger these events for their
    own account.

    SECURITY:
    The recipient is always current_user.uid.

    Android cannot choose another user's UID through this route.

    Linking and linked-Student monitoring notifications should
    be created by the backend code that performs and validates
    the actual linking operation.
    """

    # --------------------------------------------------------
    # Normalize Event
    # --------------------------------------------------------

    event_type = (
        normalize_event_type(
            request.eventType
        )
    )

    # --------------------------------------------------------
    # Validate Event
    # --------------------------------------------------------

    if (
        event_type
        not in SUPPORTED_OWN_FINANCE_EVENTS
    ):

        logger.warning(
            "Unsupported own-finance notification event. "
            "uid=%s eventType=%s",
            current_user.uid,
            event_type,
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported own-finance notification event."
            ),
        )

    # ========================================================
    # LOW ALLOWANCE
    # ========================================================

    if (
        event_type
        == EVENT_ALLOWANCE_LOW
    ):

        notification_id = (
            create_notification_if_not_recent(
                user_id=
                    current_user.uid,

                notification_type=
                    EVENT_ALLOWANCE_LOW,

                title=
                    "Low Allowance",

                message=(
                    "Your remaining allowance is "
                    "running low."
                ),

                within_hours=
                    24,
            )
        )

    # ========================================================
    # UNUSUAL SPENDING
    # ========================================================

    elif (
        event_type
        == EVENT_UNUSUAL_SPENDING
    ):

        notification_id = (
            create_notification_if_not_recent(
                user_id=
                    current_user.uid,

                notification_type=
                    EVENT_UNUSUAL_SPENDING,

                title=
                    "Unusual Spending Detected",

                message=(
                    "Your recent spending is higher "
                    "than usual."
                ),

                within_hours=
                    24,
            )
        )

    # ========================================================
    # FINANCIAL RISK
    # ========================================================

    elif (
        event_type
        == EVENT_FINANCIAL_RISK
    ):

        notification_id = (
            create_notification_if_not_recent(
                user_id=
                    current_user.uid,

                notification_type=
                    EVENT_FINANCIAL_RISK,

                title=
                    "Financial Risk Alert",

                message=(
                    "Your current spending pattern may "
                    "put your allowance at risk."
                ),

                within_hours=
                    24,
            )
        )

    # ========================================================
    # BUDGET EXCEEDED
    # ========================================================

    elif (
        event_type
        == EVENT_BUDGET_EXCEEDED
    ):

        notification_id = (
            create_notification_if_not_recent(
                user_id=
                    current_user.uid,

                notification_type=
                    EVENT_BUDGET_EXCEEDED,

                title=
                    "Budget Exceeded",

                message=(
                    "You have exceeded your current "
                    "allowance budget."
                ),

                within_hours=
                    24,
            )
        )

    # ========================================================
    # FORECAST UPDATED
    # ========================================================

    elif (
        event_type
        == EVENT_FORECAST_UPDATE
    ):

        notification_id = (
            create_notification_if_not_recent(
                user_id=
                    current_user.uid,

                notification_type=
                    EVENT_FORECAST_UPDATE,

                title=
                    "Forecast Updated",

                message=(
                    "Your allowance forecast has been "
                    "updated."
                ),

                within_hours=
                    12,
            )
        )

    # ========================================================
    # DEFENSIVE FALLBACK
    # ========================================================

    else:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported notification event.",
        )

    # ========================================================
    # DUPLICATE SKIPPED
    # ========================================================

    if (
        notification_id
        is None
    ):

        return NotificationEventResponse(
            success=True,
            notificationId=None,
            skipped=True,
            message=(
                "A recent equivalent notification "
                "already exists."
            ),
        )

    # ========================================================
    # CREATED
    # ========================================================

    logger.info(
        "Own-finance notification created. "
        "uid=%s type=%s notificationId=%s",
        current_user.uid,
        event_type,
        notification_id,
    )

    return NotificationEventResponse(
        success=True,
        notificationId=
            notification_id,
        skipped=False,
        message=(
            "Notification created successfully."
        ),
    )