from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from firebase_admin import auth as fb_auth
from firebase_admin import firestore

from services import fcm_service  # Ensures Firebase Admin is initialized.
from services.otp_service import (
    OtpServiceError,
    claim_verification_token,
    complete_verification_token,
    release_verification_token,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ============================================================
# REQUEST MODELS
# ============================================================

class ResetPasswordRequest(BaseModel):
    email: EmailStr

    newPassword: str = Field(
        min_length=6,
        max_length=128,
    )

    verificationToken: str = Field(
        min_length=1,
    )


class RegisterRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=6,
        max_length=128,
    )

    verificationToken: str = Field(
        min_length=1,
    )

    name: str = Field(
        min_length=1,
        max_length=100,
    )

    age: int = Field(
        ge=15,
        le=100,
    )

    role: str = Field(
        min_length=1,
    )


# ============================================================
# HELPERS
# ============================================================

def normalize_email(
    email: str
) -> str:
    return (
        email
        .strip()
        .lower()
    )


def normalize_name(
    name: str
) -> str:

    normalized = " ".join(
        name.strip().split()
    )

    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name is required.",
        )

    return normalized


def normalize_role(
    role: str
) -> str:

    normalized = (
        role
        .strip()
        .lower()
    )

    if normalized == "student":
        return "Student"

    if normalized == "provider":
        return "Provider"

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Role must be Student or Provider.",
    )


# ============================================================
# REGISTER
# ============================================================

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest
):

    email = normalize_email(
        str(request.email)
    )

    password = str(
        request.password
    )

    token = str(
        request.verificationToken
    ).strip()

    name = normalize_name(
        request.name
    )

    role = normalize_role(
        request.role
    )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is required.",
        )

    # --------------------------------------------------------
    # 1. Atomically claim signup verification token
    #
    # This prevents two registration requests from using
    # the same verification token simultaneously.
    # --------------------------------------------------------

    try:
        token_reference, processing_id = (
            claim_verification_token(
                email=email,
                purpose="signup",
                token=token,
            )
        )

    except OtpServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    created_user = None
    firestore_profile_created = False

    try:

        # ----------------------------------------------------
        # 2. Check whether Firebase account already exists
        # ----------------------------------------------------

        try:
            fb_auth.get_user_by_email(
                email
            )

            # Existing Firebase user found.
            release_verification_token(
                token_reference,
                processing_id,
            )

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "An account with this email "
                    "already exists."
                ),
            )

        except fb_auth.UserNotFoundError:
            # Expected result for a new registration.
            pass

        # ----------------------------------------------------
        # 3. Create Firebase Auth account
        # ----------------------------------------------------

        created_user = (
            fb_auth.create_user(
                email=email,
                password=password,
                display_name=name,
            )
        )

        # ----------------------------------------------------
        # 4. Create Firestore user profile
        # ----------------------------------------------------

        db = firestore.client()

        user_reference = (
            db.collection("users")
            .document(created_user.uid)
        )

        user_data = {
            "uid": created_user.uid,
            "email": email,

            "name": name,
            "nameLowercase": name.lower(),

            "age": request.age,
            "role": role,

            # Finora OTP verification metadata
            "emailVerified": True,
            "verificationMethod": "OTP",
            "emailVerifiedAt":
                firestore.SERVER_TIMESTAMP,

            # Linking/privacy
            "isSearchable": True,

            # Profile
            "profileImageUrl": None,

            # FCM
            "fcmToken": None,
            "fcmTokenUpdatedAt": None,

            # Timestamps
            "createdAt":
                firestore.SERVER_TIMESTAMP,

            "updatedAt":
                firestore.SERVER_TIMESTAMP,
        }

        user_reference.set(
            user_data
        )

        firestore_profile_created = True

        # ----------------------------------------------------
        # 5. Registration succeeded.
        # Permanently consume verification token.
        # ----------------------------------------------------

        complete_verification_token(
            token_reference,
            processing_id,
        )

        return {
            "success": True,
            "uid": created_user.uid,
            "message":
                "Account created successfully.",
        }

    except HTTPException:
        raise

    except Exception as exc:

        # ----------------------------------------------------
        # Registration failed.
        #
        # Roll back partially-created resources.
        # ----------------------------------------------------

        if created_user is not None:

            if firestore_profile_created:

                try:
                    firestore.client() \
                        .collection("users") \
                        .document(created_user.uid) \
                        .delete()

                except Exception:
                    pass

            try:
                fb_auth.delete_user(
                    created_user.uid
                )

            except Exception:
                pass

        # ----------------------------------------------------
        # Release verification token so the user can retry
        # while it is still within its validity period.
        # ----------------------------------------------------

        try:
            release_verification_token(
                token_reference,
                processing_id,
            )

        except Exception:
            pass

        raise HTTPException(
            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=
                f"Account creation failed: {exc}",
        ) from exc


# ============================================================
# RESET PASSWORD
# ============================================================

@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
)
def reset_password(
    request: ResetPasswordRequest
):

    email = normalize_email(
        str(request.email)
    )

    new_password = str(
        request.newPassword
    )

    token = str(
        request.verificationToken
    ).strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is required.",
        )

    # --------------------------------------------------------
    # 1. Atomically claim password-reset verification token
    # --------------------------------------------------------

    try:
        token_reference, processing_id = (
            claim_verification_token(
                email=email,
                purpose="password_reset",
                token=token,
            )
        )

    except OtpServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # --------------------------------------------------------
    # 2. Find Firebase Auth user
    # --------------------------------------------------------

    try:

        user = (
            fb_auth.get_user_by_email(
                email
            )
        )

    except fb_auth.UserNotFoundError:

        try:
            release_verification_token(
                token_reference,
                processing_id,
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    except Exception as exc:

        try:
            release_verification_token(
                token_reference,
                processing_id,
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=
                f"Failed to look up user: {exc}",
        ) from exc

    # --------------------------------------------------------
    # 3. Update password through Firebase Admin
    # --------------------------------------------------------

    try:

        fb_auth.update_user(
            user.uid,
            password=new_password,
        )

    except Exception as exc:


         # Password update failed
         # Release token so user can retry instead of
         # requiring another OTP immediately.
         
        try:
            release_verification_token(
                token_reference,
                processing_id,
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=
                f"Failed to update password: {exc}",
        ) from exc

    # --------------------------------------------------------
    # 4. Password update succeeded.
    # Permanently consume verification token.
    # --------------------------------------------------------

    try:

        complete_verification_token(
            token_reference,
            processing_id,
        )

    except OtpServiceError as exc:

        # IMPORTANT:
         #The password has already been successfully updated
         #in Firebase at this point
         # Do NOT attempt to restore the previous password,
         # because the backend intentionally does not know it.
         
        raise HTTPException(
            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Password was updated successfully, "
                "but verification-token cleanup failed. "
                f"{exc}"
            ),
        ) from exc

    return {
        "success": True,
        "message":
            "Password updated successfully.",
    }