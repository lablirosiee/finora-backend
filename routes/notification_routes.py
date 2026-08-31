import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from firebase_admin import firestore

from schemas.notification_schemas import (
    NotificationEventRequest,
    NotificationEventResponse,
)

from services.auth_service import (
    AuthenticatedUser,
    get_current_user,
)

from services.notification_service import (
    create_and_send_notification,
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
# Supported Android Events
# ============================================================

EVENT_LINK_REQUEST = "LINK_REQUEST"
EVENT_LINK_APPROVED = "LINK_APPROVED"
EVENT_LINK_DECLINED = "LINK_DECLINED"
EVENT_LINK_EXPIRED = "LINK_EXPIRED"
EVENT_ACCOUNT_UNLINKED = "ACCOUNT_UNLINKED"

EVENT_ALLOWANCE_LOW = "ALLOWANCE_LOW"
EVENT_UNUSUAL_SPENDING = "UNUSUAL_SPENDING"
EVENT_FINANCIAL_RISK = "FINANCIAL_RISK"
EVENT_BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
EVENT_FORECAST_UPDATE = "FORECAST_UPDATE"


SUPPORTED_EVENTS = {
    EVENT_LINK_REQUEST,
    EVENT_LINK_APPROVED,
    EVENT_LINK_DECLINED,
    EVENT_LINK_EXPIRED,
    EVENT_ACCOUNT_UNLINKED,
    EVENT_ALLOWANCE_LOW,
    EVENT_UNUSUAL_SPENDING,
    EVENT_FINANCIAL_RISK,
    EVENT_BUDGET_EXCEEDED,
    EVENT_FORECAST_UPDATE,
}


# ============================================================
# Helpers
# ============================================================

def normalize_event_type(
    event_type: str,
) -> str:
    return (
        event_type
        .strip()
        .upper()
    )


def get_user_profile(
    user_id: str,
) -> dict:
    db = firestore.client()

    snapshot = (
        db.collection("users")
        .document(user_id)
        .get()
    )

    if not snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return snapshot.to_dict() or {}


def require_same_user(
    authenticated_user: AuthenticatedUser,
    expected_user_id: str,
) -> None:
    """
    Ensure the authenticated Firebase user matches the user
    who is allowed to trigger this operation.
    """

    if authenticated_user.uid != expected_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to perform this action.",
        )


# ============================================================
# Production Notification Event Endpoint
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

    event_type = normalize_event_type(
        request.eventType
    )

    target_user_id = (
        request.targetUserId.strip()
    )

    student_id = (
        request.studentId.strip()
    )


    if event_type not in SUPPORTED_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported notification event.",
        )


    # ========================================================
    # LINK REQUEST
    # ========================================================

    if event_type == EVENT_LINK_REQUEST:

        if not target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target user ID is required.",
            )

        sender_profile = get_user_profile(
            current_user.uid
        )

        sender_name = str(
            sender_profile.get("name")
            or "A Finora user"
        ).strip()

        notification_id = (
            create_and_send_notification(
                user_id=target_user_id,
                notification_type="LINK_REQUEST",
                title="New Link Request",
                message=(
                    f"{sender_name} sent you a "
                    "link request."
                ),
                student_id=student_id,
            )
        )

        return NotificationEventResponse(
            success=True,
            notificationId=notification_id,
            skipped=False,
            message="Link request notification sent.",
        )


    # ========================================================
    # LINK APPROVED
    # ========================================================

    if event_type == EVENT_LINK_APPROVED:

        if not target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target user ID is required.",
            )

        notification_id = (
            create_and_send_notification(
                user_id=target_user_id,
                notification_type="LINK_APPROVED",
                title="Link Request Approved",
                message=(
                    "Your link request has been approved."
                ),
                student_id=student_id,
            )
        )

        return NotificationEventResponse(
            success=True,
            notificationId=notification_id,
            skipped=False,
            message="Approval notification sent.",
        )


    # ========================================================
    # LINK DECLINED
    # ========================================================

    if event_type == EVENT_LINK_DECLINED:

        if not target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target user ID is required.",
            )

        notification_id = (
            create_and_send_notification(
                user_id=target_user_id,
                notification_type="LINK_DECLINED",
                title="Link Request Declined",
                message=(
                    "Your link request was declined."
                ),
                student_id=student_id,
            )
        )

        return NotificationEventResponse(
            success=True,
            notificationId=notification_id,
            skipped=False,
            message="Decline notification sent.",
        )


    # ========================================================
    # LINK EXPIRED
    # ========================================================

    if event_type == EVENT_LINK_EXPIRED:

        if not target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target user ID is required.",
            )

        notification_id = (
            create_and_send_notification(
                user_id=target_user_id,
                notification_type="LINK_EXPIRED",
                title="Link Request Expired",
                message=(
                    "A Finora link request has expired."
                ),
                student_id=student_id,
            )
        )

        return NotificationEventResponse(
            success=True,
            notificationId=notification_id,
            skipped=False,
            message="Expiration notification sent.",
        )


    # ========================================================
    # ACCOUNT UNLINKED
    # ========================================================

    if event_type == EVENT_ACCOUNT_UNLINKED:

        if not target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target user ID is required.",
            )

        notification_id = (
            create_and_send_notification(
                user_id=target_user_id,
                notification_type="ACCOUNT_UNLINKED",
                title="Account Unlinked",
                message=(
                    "A linked Finora account has been "
                    "disconnected."
                ),
                student_id=student_id,
            )
        )

        return NotificationEventResponse(
            success=True,
            notificationId=notification_id,
            skipped=False,
            message="Unlink notification sent.",
        )


    # ========================================================
    # STUDENT FINANCIAL EVENTS
    #
    # The authenticated user must be the student.
    # ========================================================

    require_same_user(
        current_user,
        current_user.uid,
    )


    if event_type == EVENT_ALLOWANCE_LOW:

        notification_id = (
            create_notification_if_not_recent(
                user_id=current_user.uid,
                notification_type="ALLOWANCE_LOW",
                title="Low Allowance",
                message=(
                    "Your remaining allowance is "
                    "running low."
                ),
                within_hours=24,
            )
        )


    elif event_type == EVENT_UNUSUAL_SPENDING:

        notification_id = (
            create_notification_if_not_recent(
                user_id=current_user.uid,
                notification_type="UNUSUAL_SPENDING",
                title="Unusual Spending Detected",
                message=(
                    "Your recent spending is higher "
                    "than usual."
                ),
                within_hours=24,
            )
        )


    elif event_type == EVENT_FINANCIAL_RISK:

        notification_id = (
            create_notification_if_not_recent(
                user_id=current_user.uid,
                notification_type="FINANCIAL_RISK",
                title="Financial Risk Alert",
                message=(
                    "Your current spending pattern may "
                    "put your allowance at risk."
                ),
                within_hours=24,
            )
        )


    elif event_type == EVENT_BUDGET_EXCEEDED:

        notification_id = (
            create_notification_if_not_recent(
                user_id=current_user.uid,
                notification_type="BUDGET_EXCEEDED",
                title="Budget Exceeded",
                message=(
                    "You have exceeded your current "
                    "allowance budget."
                ),
                within_hours=24,
            )
        )


    elif event_type == EVENT_FORECAST_UPDATE:

        notification_id = (
            create_notification_if_not_recent(
                user_id=current_user.uid,
                notification_type="FORECAST_UPDATE",
                title="Forecast Updated",
                message=(
                    "Your allowance forecast has been "
                    "updated."
                ),
                within_hours=12,
            )
        )


    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported notification event.",
        )


    if notification_id is None:

        return NotificationEventResponse(
            success=True,
            notificationId=None,
            skipped=True,
            message=(
                "A recent notification already exists."
            ),
        )


    return NotificationEventResponse(
        success=True,
        notificationId=notification_id,
        skipped=False,
        message="Notification created successfully.",
    )