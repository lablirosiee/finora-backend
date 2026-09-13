import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from schemas.fcm_schemas import (
    FcmSendRequest,
    FcmSendResponse,
)

from services.auth_service import (
    AuthenticatedUser,
    get_current_user,
)

from services.fcm_service import (
    send_push_to_user,
)


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Router
# ============================================================

router = APIRouter(
    prefix="/fcm",
    tags=["FCM"],
)


# ============================================================
# IMPORTANT
#
# Production notifications should NOT normally call this route.
#
# The normal production path is:
#
# notification_service.py
#        ↓
# create Firestore notification
#        ↓
# send_push_to_user()
#
# This route exists only as an authenticated diagnostic endpoint.
# ============================================================


# ============================================================
# Authenticated FCM Test
# ============================================================

@router.post(
    "/send-test",
    response_model=FcmSendResponse,
    status_code=status.HTTP_200_OK,
)
def send_test_push(
    request: FcmSendRequest,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
) -> FcmSendResponse:
    """
    Send a data-only FCM push to the currently authenticated
    Finora account for development/testing.

    SECURITY:
    The caller may only send a test push to their own account.

    This endpoint does NOT create a Firestore notification.
    """

    requested_user_id = (
        request.userId.strip()
    )

    # --------------------------------------------------------
    # Recipient Validation
    # --------------------------------------------------------

    if not requested_user_id:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID is required.",
        )

    if (
        requested_user_id
        != current_user.uid
    ):

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You may only send a test notification "
                "to your own account."
            ),
        )

    # --------------------------------------------------------
    # Send
    # --------------------------------------------------------

    try:

        message_id = send_push_to_user(
            user_id=current_user.uid,
            notification_type=request.type,
            title=request.title,
            message=request.message,
            notification_id=request.notificationId,
            student_id=request.studentId,
        )

        return FcmSendResponse(
            success=True,
            messageId=message_id,
        )

    except ValueError as exc:

        logger.warning(
            "FCM test request rejected for user %s: %s",
            current_user.uid,
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        logger.exception(
            "Unexpected error while sending test FCM push "
            "for user %s.",
            current_user.uid,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send FCM notification.",
        ) from exc