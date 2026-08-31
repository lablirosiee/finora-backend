import logging

from fastapi import APIRouter, HTTPException, status

from schemas.fcm_schemas import (
    FcmSendRequest,
    FcmSendResponse,
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
# Test FCM Push
# ============================================================

@router.post(
    "/send-test",
    response_model=FcmSendResponse,
    status_code=status.HTTP_200_OK,
)
def send_test_push(
    request: FcmSendRequest,
) -> FcmSendResponse:
    """
    Send a data-only FCM push for development/testing.

    IMPORTANT:
    This endpoint does NOT create a Firestore notification.

    Production notifications must go through
    notification_service.create_and_send_notification().
    """

    try:

        message_id = send_push_to_user(
            user_id=request.userId,
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
            "FCM test request rejected: %s",
            exc,
        )


        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


    except Exception:

        logger.exception(
            "Unexpected error while sending test FCM push."
        )


        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send FCM notification.",
        )