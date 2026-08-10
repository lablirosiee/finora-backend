from fastapi import APIRouter, HTTPException, status

from schemas.otp_schemas import (
    OtpEmailRequest,
    OtpEmailResponse,
)
from services.email_service import (
    EmailAuthenticationError,
    EmailConfigurationError,
    EmailDeliveryError,
    send_otp_email,
)


router = APIRouter(
    prefix="/otp",
    tags=["OTP Authentication"],
)


@router.post(
    "/send",
    response_model=OtpEmailResponse,
    status_code=status.HTTP_200_OK,
)
def send_otp(
    request: OtpEmailRequest,
) -> OtpEmailResponse:
    recipient_email = str(request.email).strip()
    otp = request.otp.strip()

    try:
        send_otp_email(
            recipient_email=recipient_email,
            otp=otp,
        )

    except EmailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    except EmailAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return OtpEmailResponse(
        success=True,
        message="OTP email sent successfully.",
    )