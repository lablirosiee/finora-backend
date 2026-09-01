import logging
from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from firebase_admin import auth as fb_auth


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    uid: str
    email: str = ""


def verify_firebase_id_token(
    id_token: str,
) -> AuthenticatedUser:

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

        logger.exception(
            "Firebase ID token verification failed."
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to authenticate request.",
        ) from exc

    uid = str(
        decoded_token.get("uid")
        or decoded_token.get("sub")
        or ""
    ).strip()

    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token does not contain a user ID.",
        )

    email = str(
        decoded_token.get("email")
        or ""
    ).strip()

    return AuthenticatedUser(
        uid=uid,
        email=email,
    )


def get_current_user(
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
    ),
) -> AuthenticatedUser:

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required.",
        )

    parts = authorization.strip().split(
        " ",
        1,
    )

    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
        or not parts[1].strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer authentication.",
        )

    return verify_firebase_id_token(
        parts[1]
    )