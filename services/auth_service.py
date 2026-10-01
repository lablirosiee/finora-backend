import logging
from dataclasses import dataclass

from fastapi import (
    Depends,
    HTTPException,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from firebase_admin import auth as fb_auth

# Ensures Firebase Admin SDK has been initialized.
from services import fcm_service  # noqa: F401


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Bearer Authentication Scheme
# ============================================================

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="FirebaseBearer",
    description=(
        "Enter a valid Firebase Authentication ID token."
    ),
)


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

    normalized_token = str(
        id_token or ""
    ).strip()

    if not normalized_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
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
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from exc

    except fb_auth.RevokedIdTokenError as exc:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from exc

    except fb_auth.InvalidIdTokenError as exc:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from exc

    except Exception as exc:

        logger.warning(
            "Firebase ID token verification failed: %s",
            type(exc).__name__,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from exc


    # --------------------------------------------------------
    # Extract Firebase UID
    # --------------------------------------------------------

    uid = str(
        decoded_token.get("uid")
        or decoded_token.get("sub")
        or ""
    ).strip()

    if not uid:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has no user ID.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )


    # --------------------------------------------------------
    # Optional Email
    # --------------------------------------------------------

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
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> AuthenticatedUser:
    """
    Read and verify:

        Authorization: Bearer <Firebase-ID-token>

    HTTPBearer also exposes Firebase Bearer authentication
    correctly in FastAPI's OpenAPI / Swagger documentation.
    """

    if credentials is None:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )


    # --------------------------------------------------------
    # Validate Authentication Scheme
    # --------------------------------------------------------

    scheme = str(
        credentials.scheme or ""
    ).strip()

    if scheme.lower() != "bearer":

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


    # --------------------------------------------------------
    # Extract Firebase ID Token
    # --------------------------------------------------------

    token = str(
        credentials.credentials or ""
    ).strip()

    if not token:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )


    return verify_firebase_id_token(
        token
    )