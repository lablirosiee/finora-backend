from fastapi import APIRouter, HTTPException, status

from schemas.otp_schemas import (
    OtpRequest,
    OtpRequestResponse,
    OtpVerifyRequest,
    OtpVerifyResponse,
)
from services.otp_service import (
    request_otp,
    verify_otp,
    OtpServiceError,
)


router = APIRouter(
    prefix="/otp",
    tags=["OTP Authentication"],
)


@router.post(
    "/request",
    response_model=OtpRequestResponse,
    status_code=status.HTTP_200_OK,
)
def request_endpoint(
    request: OtpRequest,
) -> OtpRequestResponse:

    recipient_email = (
        str(request.email)
        .strip()
        .lower()
    )

    purpose = (
        str(request.purpose)
        .strip()
    )

    try:
        request_otp(
            recipient_email,
            purpose,
        )

    except OtpServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        print(
            "OTP REQUEST ERROR:",
            type(exc).__name__,
            str(exc),
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP email.",
        ) from exc

    return OtpRequestResponse(
        success=True,
        message="OTP sent.",
    )


@router.post(
    "/verify",
    response_model=OtpVerifyResponse,
    status_code=status.HTTP_200_OK,
)
def verify_endpoint(
    request: OtpVerifyRequest,
) -> OtpVerifyResponse:

    recipient_email = (
        str(request.email)
        .strip()
        .lower()
    )

    purpose = (
        str(request.purpose)
        .strip()
    )

    otp = (
        str(request.otp)
        .strip()
    )

    try:
        verification_token = verify_otp(
            recipient_email,
            purpose,
            otp,
        )

    except OtpServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        print(
            "OTP VERIFY ERROR:",
            type(exc).__name__,
            str(exc),
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify OTP.",
        ) from exc

    return OtpVerifyResponse(
        success=True,
        verificationToken=verification_token,
    )