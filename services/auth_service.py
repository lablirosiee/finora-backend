import logging
from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from firebase_admin import auth as fb_auth

# Ensures Firebase Admin SDK has been initialized.
from services import fcm_service  # noqa: F401


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Authenticated User
# ============================================================

@dataclass(frozen=True)
class AuthenticatedUser:
    uid: str
    email: str = ""


# ============================================================
# Verify Firebase ID Token
# ============================================================

def verify_firebase_id_token(
    id_token: str,
) -> AuthenticatedUser:
    """
    Verify a Firebase Authentication ID token.

    The token must come from a user who is currently signed
    in to Finora on Android.

    Returns:
        AuthenticatedUser containing the verified Firebase UID.

    Raises:
        HTTPException:
            401 when the token is missing, invalid, expired,
            revoked, or otherwise cannot be verified.
    """

    normalized_token = id_token.strip()

    if not normalized_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required.",
        )

    try:
        decoded_token = fb_auth.verify_id_token(
            normalized_token,
            check_revoked=True,
        )

    except fb_auth.ExpiredIdTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
        ) from exc

    except fb_auth.RevokedIdTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked.",
        ) from exc

    except fb_auth.InvalidIdTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        ) from exc

    except Exception as exc:
        logger.warning(
            "Firebase ID token verification failed: %s",
            type(exc).__name__,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
        ) from exc

    uid = str(
        decoded_token.get("uid")
        or decoded_token.get("sub")
        or ""
    ).strip()

    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has no user ID.",
        )

    email = str(
        decoded_token.get("email")
        or ""
    ).strip()

    return AuthenticatedUser(
        uid=uid,
        email=email,
    )


# ============================================================
# FastAPI Authentication Dependency
# ============================================================

def get_current_user(
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
    ),
) -> AuthenticatedUser:
    """
    Read and verify:

        Authorization: Bearer <Firebase-ID-token>
    """

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    parts = authorization.strip().split()

    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
        or not parts[1].strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authorization header must use "
                "Bearer authentication."
            ),
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    return verify_firebase_id_token(
        parts[1]
    )