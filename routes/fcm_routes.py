from fastapi import APIRouter, HTTPException

from schemas.fcm_schemas import (
    FcmSendRequest,
    FcmSendResponse,
)

from services.fcm_service import (
    send_push_to_user,
)


router = APIRouter(
    prefix="/fcm",
    tags=["FCM"],
)


@router.post(
    "/send-test",
    response_model=FcmSendResponse,
)
def send_test_push(
    request: FcmSendRequest,
):
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
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"FCM send failed: {exc}",
        )