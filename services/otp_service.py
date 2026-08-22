import hashlib
import os
import secrets
import time
import uuid

from firebase_admin import firestore

from services import fcm_service  # Ensures Firebase Admin is initialized.
from services.email_service import send_otp_email


# ============================================================
# CONFIGURATION
# ============================================================

OTP_EXPIRY_SECONDS = int(
    os.getenv(
        "OTP_EXPIRY_SECONDS",
        "600",
    )
)

OTP_RESEND_COOLDOWN = int(
    os.getenv(
        "OTP_RESEND_COOLDOWN",
        "60",
    )
)

OTP_ATTEMPT_LIMIT = int(
    os.getenv(
        "OTP_ATTEMPT_LIMIT",
        "5",
    )
)

VERIFICATION_TOKEN_EXPIRY = int(
    os.getenv(
        "VERIFICATION_TOKEN_EXPIRY",
        "900",
    )
)

TOKEN_PROCESSING_LEASE_SECONDS = int(
    os.getenv(
        "TOKEN_PROCESSING_LEASE_SECONDS",
        "120",
    )
)


# ============================================================
# FIRESTORE
# ============================================================

db = firestore.client()

OTPS_COLLECTION = db.collection(
    "otps"
)

TOKENS_COLLECTION = db.collection(
    "verification_tokens"
)


# ============================================================
# EXCEPTIONS
# ============================================================

class OtpServiceError(Exception):
    pass


class OtpCooldownError(OtpServiceError):
    pass


# ============================================================
# HELPERS
# ============================================================

def _now() -> int:
    return int(
        time.time()
    )


def _normalize_email(
    email: str
) -> str:

    normalized = (
        email
        .strip()
        .lower()
    )

    if not normalized:
        raise OtpServiceError(
            "Email address is required."
        )

    return normalized


def _validate_purpose(
    purpose: str
) -> str:

    normalized = (
        purpose
        .strip()
        .lower()
    )

    if normalized not in (
        "signup",
        "password_reset",
    ):
        raise OtpServiceError(
            "Invalid OTP purpose."
        )

    return normalized


def _hash_value(
    value: str,
    salt: str
) -> str:

    return hashlib.pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()


def _get_latest_unused_otp(
    email: str,
    purpose: str
):

    query = (
        OTPS_COLLECTION
        .where(
            "email",
            "==",
            email
        )
        .where(
            "purpose",
            "==",
            purpose
        )
        .where(
            "used",
            "==",
            False
        )
        .order_by(
            "created_at",
            direction=
            firestore.Query.DESCENDING
        )
        .limit(1)
    )

    docs = query.get()

    if not docs:
        return None

    return docs[0]


def _get_latest_available_token(
    email: str,
    purpose: str
):

    query = (
        TOKENS_COLLECTION
        .where(
            "email",
            "==",
            email
        )
        .where(
            "purpose",
            "==",
            purpose
        )
        .where(
            "used",
            "==",
            False
        )
        .order_by(
            "created_at",
            direction=
            firestore.Query.DESCENDING
        )
        .limit(10)
    )

    docs = query.get()

    if not docs:
        return []

    return docs


# ============================================================
# REQUEST OTP
# ============================================================

def request_otp(
    email: str,
    purpose: str
) -> None:

    email = _normalize_email(
        email
    )

    purpose = _validate_purpose(
        purpose
    )

    now = _now()

    # --------------------------------------------------------
    # Resend cooldown
    # --------------------------------------------------------

    latest_doc = (
        _get_latest_unused_otp(
            email,
            purpose
        )
    )

    if latest_doc is not None:

        latest_data = (
            latest_doc.to_dict()
            or {}
        )

        last_sent_at = int(
            latest_data.get(
                "last_sent_at",
                0
            )
            or 0
        )

        if (
            last_sent_at > 0 and
            now - last_sent_at
            < OTP_RESEND_COOLDOWN
        ):

            wait_seconds = (
                OTP_RESEND_COOLDOWN -
                (now - last_sent_at)
            )

            raise OtpCooldownError(
                f"Please wait {wait_seconds} "
                "seconds before requesting "
                "another OTP."
            )

    # --------------------------------------------------------
    # Generate OTP
    # --------------------------------------------------------

    otp = (
        f"{secrets.randbelow(1_000_000):06d}"
    )

    salt = (
        secrets.token_hex(16)
    )

    otp_hash = _hash_value(
        otp,
        salt
    )

    expires_at = (
        now +
        OTP_EXPIRY_SECONDS
    )

    otp_reference = (
        OTPS_COLLECTION
        .document()
    )

    otp_record = {
        "email": email,
        "purpose": purpose,

        "otp_hash": otp_hash,
        "salt": salt,

        "created_at": now,
        "expires_at": expires_at,
        "last_sent_at": now,

        "attempts_left":
            OTP_ATTEMPT_LIMIT,

        "used": False,
    }

    # --------------------------------------------------------
    # Save hashed OTP
    # --------------------------------------------------------

    otp_reference.set(
        otp_record
    )

    # --------------------------------------------------------
    # Send through Brevo
    #
    # If email delivery fails, invalidate this OTP so the user
    # is not blocked by a code they never received.
    # --------------------------------------------------------

    try:

        send_otp_email(
            recipient_email=email,
            otp=otp,
        )

    except Exception:

        try:
            otp_reference.update(
                {
                    "used": True,
                    "delivery_failed": True,
                }
            )
        except Exception:
            pass

        raise


# ============================================================
# VERIFY OTP
# ============================================================

def verify_otp(
    email: str,
    purpose: str,
    otp: str
) -> str:

    email = _normalize_email(
        email
    )

    purpose = _validate_purpose(
        purpose
    )

    otp = otp.strip()

    if (
        len(otp) != 6 or
        not otp.isdigit()
    ):
        raise OtpServiceError(
            "OTP must contain exactly 6 digits."
        )

    latest_doc = (
        _get_latest_unused_otp(
            email,
            purpose
        )
    )

    if latest_doc is None:

        raise OtpServiceError(
            "No active OTP was found."
        )

    otp_reference = (
        latest_doc.reference
    )

    transaction = (
        db.transaction()
    )

    @firestore.transactional
    def verify_in_transaction(
        transaction
    ):

        snapshot = (
            otp_reference.get(
                transaction=transaction
            )
        )

        if not snapshot.exists:
            raise OtpServiceError(
                "OTP no longer exists."
            )

        data = (
            snapshot.to_dict()
            or {}
        )

        if bool(
            data.get(
                "used",
                False
            )
        ):
            raise OtpServiceError(
                "OTP has already been used."
            )

        now = _now()

        expires_at = int(
            data.get(
                "expires_at",
                0
            )
            or 0
        )

        if (
            expires_at <= 0 or
            now > expires_at
        ):

            transaction.update(
                otp_reference,
                {
                    "used": True,
                    "invalidated_reason":
                        "expired",
                }
            )

            raise OtpServiceError(
                "OTP has expired."
            )

        attempts_left = int(
            data.get(
                "attempts_left",
                0
            )
            or 0
        )

        if attempts_left <= 0:

            transaction.update(
                otp_reference,
                {
                    "used": True,
                    "attempts_left": 0,
                    "invalidated_reason":
                        "attempt_limit",
                }
            )

            raise OtpServiceError(
                "OTP has been invalidated."
            )

        salt = str(
            data.get(
                "salt",
                ""
            )
        )

        stored_hash = str(
            data.get(
                "otp_hash",
                ""
            )
        )

        if (
            not salt or
            not stored_hash
        ):
            raise OtpServiceError(
                "OTP record is invalid."
            )

        computed_hash = (
            _hash_value(
                otp,
                salt
            )
        )

        if not secrets.compare_digest(
            computed_hash,
            stored_hash
        ):

            remaining = (
                attempts_left - 1
            )

            updates = {
                "attempts_left":
                    max(
                        remaining,
                        0
                    )
            }

            if remaining <= 0:

                updates.update(
                    {
                        "used": True,
                        "invalidated_reason":
                            "attempt_limit",
                    }
                )

            transaction.update(
                otp_reference,
                updates
            )

            if remaining <= 0:

                raise OtpServiceError(
                    "Too many failed attempts. "
                    "OTP invalidated."
                )

            raise OtpServiceError(
                f"Invalid OTP. "
                f"{remaining} attempts remaining."
            )

        # ----------------------------------------------------
        # OTP valid
        # Consume it atomically.
        # ----------------------------------------------------

        transaction.update(
            otp_reference,
            {
                "used": True,
                "verified_at": now,
            }
        )

        return now

    verified_at = (
        verify_in_transaction(
            transaction
        )
    )

    # --------------------------------------------------------
    # Issue verification token
    # --------------------------------------------------------

    token = (
        secrets.token_urlsafe(32)
    )

    token_salt = (
        secrets.token_hex(16)
    )

    token_hash = (
        _hash_value(
            token,
            token_salt
        )
    )

    token_reference = (
        TOKENS_COLLECTION
        .document()
    )

    token_reference.set(
        {
            "email": email,
            "purpose": purpose,

            "token_hash":
                token_hash,

            "salt":
                token_salt,

            "created_at":
                verified_at,

            "expires_at":
                (
                    verified_at +
                    VERIFICATION_TOKEN_EXPIRY
                ),

            "used": False,

            
             #processing fields allow a token to be
             # safely claimed for registration/password
             #reset without permanently consuming it
             # before the sensitive operation succeeds.
             
            "processing": False,
            "processing_id": None,
            "processing_until": 0,
        }
    )

    return token


# ============================================================
# FIND TOKEN
# ============================================================

def _find_matching_token(
    email: str,
    purpose: str,
    token: str
):

    email = _normalize_email(
        email
    )

    purpose = _validate_purpose(
        purpose
    )

    token = token.strip()

    if not token:
        raise OtpServiceError(
            "Verification token is required."
        )

    docs = (
        _get_latest_available_token(
            email,
            purpose
        )
    )

    if not docs:

        raise OtpServiceError(
            "Invalid or missing verification token."
        )

    now = _now()

    for doc in docs:

        data = (
            doc.to_dict()
            or {}
        )

        if bool(
            data.get(
                "used",
                False
            )
        ):
            continue

        expires_at = int(
            data.get(
                "expires_at",
                0
            )
            or 0
        )

        if (
            expires_at <= 0 or
            now > expires_at
        ):
            continue

        salt = str(
            data.get(
                "salt",
                ""
            )
        )

        stored_hash = str(
            data.get(
                "token_hash",
                ""
            )
        )

        if (
            not salt or
            not stored_hash
        ):
            continue

        computed_hash = (
            _hash_value(
                token,
                salt
            )
        )

        if secrets.compare_digest(
            computed_hash,
            stored_hash
        ):

            return doc

    raise OtpServiceError(
        "Invalid or expired verification token."
    )


# ============================================================
# VALIDATE TOKEN
# ============================================================

def validate_verification_token(
    email: str,
    purpose: str,
    token: str
):

    """
    Validate without changing token state.

    Useful for inspection, but sensitive actions should use
    claim_verification_token() instead.
    """

    return _find_matching_token(
        email,
        purpose,
        token
    )


# ============================================================
# CLAIM TOKEN
# ============================================================

def claim_verification_token(
    email: str,
    purpose: str,
    token: str
):

    """
    Atomically claim a verification token before performing
    a sensitive operation.

    This prevents two concurrent requests from using the same
    token at the same time.

    Returns:
        (DocumentReference, processing_id)
    """

    token_doc = (
        _find_matching_token(
            email,
            purpose,
            token
        )
    )

    token_reference = (
        token_doc.reference
    )

    processing_id = (
        uuid.uuid4().hex
    )

    transaction = (
        db.transaction()
    )

    @firestore.transactional
    def claim_in_transaction(
        transaction
    ):

        snapshot = (
            token_reference.get(
                transaction=transaction
            )
        )

        if not snapshot.exists:

            raise OtpServiceError(
                "Verification token no longer exists."
            )

        data = (
            snapshot.to_dict()
            or {}
        )

        now = _now()

        if bool(
            data.get(
                "used",
                False
            )
        ):

            raise OtpServiceError(
                "Verification token has already been used."
            )

        expires_at = int(
            data.get(
                "expires_at",
                0
            )
            or 0
        )

        if (
            expires_at <= 0 or
            now > expires_at
        ):

            transaction.update(
                token_reference,
                {
                    "used": True,
                    "processing": False,
                }
            )

            raise OtpServiceError(
                "Verification token has expired."
            )

        processing = bool(
            data.get(
                "processing",
                False
            )
        )

        processing_until = int(
            data.get(
                "processing_until",
                0
            )
            or 0
        )

        
         # Allow recovery from an abandoned claim after
         # its short processing lease expires.
         
        if (
            processing and
            processing_until > now
        ):

            raise OtpServiceError(
                "Verification token is already being processed."
            )

        transaction.update(
            token_reference,
            {
                "processing": True,
                "processing_id":
                    processing_id,
                "processing_until":
                    (
                        now +
                        TOKEN_PROCESSING_LEASE_SECONDS
                    ),
            }
        )

    claim_in_transaction(
        transaction
    )

    return (
        token_reference,
        processing_id
    )


# ============================================================
# COMPLETE TOKEN
# ============================================================

def complete_verification_token(
    token_reference,
    processing_id: str
) -> None:

    transaction = (
        db.transaction()
    )

    @firestore.transactional
    def complete_in_transaction(
        transaction
    ):

        snapshot = (
            token_reference.get(
                transaction=transaction
            )
        )

        if not snapshot.exists:

            raise OtpServiceError(
                "Verification token no longer exists."
            )

        data = (
            snapshot.to_dict()
            or {}
        )

        if bool(
            data.get(
                "used",
                False
            )
        ):
            return

        current_processing_id = str(
            data.get(
                "processing_id",
                ""
            )
            or ""
        )

        if (
            current_processing_id !=
            processing_id
        ):

            raise OtpServiceError(
                "Verification token ownership mismatch."
            )

        transaction.update(
            token_reference,
            {
                "used": True,
                "used_at": _now(),

                "processing": False,
                "processing_id": None,
                "processing_until": 0,
            }
        )

    complete_in_transaction(
        transaction
    )


# ============================================================
# RELEASE TOKEN
# ============================================================

def release_verification_token(
    token_reference,
    processing_id: str
) -> None:

    """
    Release the token after an operation fails so the user can
    safely retry while the verification token is still valid.
    """

    transaction = (
        db.transaction()
    )

    @firestore.transactional
    def release_in_transaction(
        transaction
    ):

        snapshot = (
            token_reference.get(
                transaction=transaction
            )
        )

        if not snapshot.exists:
            return

        data = (
            snapshot.to_dict()
            or {}
        )

        if bool(
            data.get(
                "used",
                False
            )
        ):
            return

        current_processing_id = str(
            data.get(
                "processing_id",
                ""
            )
            or ""
        )

        if (
            current_processing_id !=
            processing_id
        ):
            return

        transaction.update(
            token_reference,
            {
                "processing": False,
                "processing_id": None,
                "processing_until": 0,
            }
        )

    release_in_transaction(
        transaction
    )


# ============================================================
# LEGACY COMPATIBILITY HELPER
# ============================================================

def consume_verification_token(
    email: str,
    purpose: str,
    token: str
) -> None:

    """
    Compatibility wrapper.

    New sensitive endpoints should prefer:

        claim_verification_token()
        complete_verification_token()
        release_verification_token()

    This function remains only so existing imports do not
    immediately break during migration.
    """

    token_reference, processing_id = (
        claim_verification_token(
            email,
            purpose,
            token
        )
    )

    complete_verification_token(
        token_reference,
        processing_id
    )