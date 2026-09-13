import logging
from typing import Final

import firebase_admin
from firebase_admin import credentials, firestore, messaging

from config import FIREBASE_SERVICE_ACCOUNT_PATH


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Firebase Configuration
# ============================================================

SERVICE_ACCOUNT_PATH = FIREBASE_SERVICE_ACCOUNT_PATH


# ============================================================
# Firestore Collections / Fields
# ============================================================

USERS_COLLECTION: Final[str] = "users"

FIELD_FCM_TOKEN: Final[str] = "fcmToken"

FIELD_FCM_TOKEN_UPDATED_AT: Final[str] = (
    "fcmTokenUpdatedAt"
)


# ============================================================
# Canonical Notification Types
#
# IMPORTANT:
# These values must remain aligned with:
#
# - Android NotificationHelper.kt
# - FinoraFirebaseMessagingService.kt
# - NotificationRepository.kt
# - notification_service.py
# ============================================================

TYPE_LINK_REQUEST: Final[str] = (
    "LINK_REQUEST"
)

TYPE_LINK_APPROVED: Final[str] = (
    "LINK_APPROVED"
)

TYPE_LINK_DECLINED: Final[str] = (
    "LINK_DECLINED"
)

TYPE_LINK_EXPIRED: Final[str] = (
    "LINK_EXPIRED"
)

TYPE_ACCOUNT_UNLINKED: Final[str] = (
    "ACCOUNT_UNLINKED"
)


# ------------------------------------------------------------
# OWN FINANCIAL NOTIFICATIONS
#
# These may belong to either a Student or Provider.
# ------------------------------------------------------------

TYPE_ALLOWANCE_LOW: Final[str] = (
    "ALLOWANCE_LOW"
)

TYPE_UNUSUAL_SPENDING: Final[str] = (
    "UNUSUAL_SPENDING"
)

TYPE_FINANCIAL_RISK: Final[str] = (
    "FINANCIAL_RISK"
)

TYPE_BUDGET_EXCEEDED: Final[str] = (
    "BUDGET_EXCEEDED"
)

TYPE_FORECAST_UPDATE: Final[str] = (
    "FORECAST_UPDATE"
)


# ------------------------------------------------------------
# PROVIDER MONITORING NOTIFICATIONS
#
# These concern a linked Student.
# ------------------------------------------------------------

TYPE_STUDENT_ALLOWANCE_LOW: Final[str] = (
    "STUDENT_ALLOWANCE_LOW"
)

TYPE_STUDENT_UNUSUAL_SPENDING: Final[str] = (
    "STUDENT_UNUSUAL_SPENDING"
)

TYPE_STUDENT_FINANCIAL_RISK: Final[str] = (
    "STUDENT_FINANCIAL_RISK"
)


# ------------------------------------------------------------
# LOCAL REMINDER TYPES
#
# Android currently creates these locally through WorkManager.
# They remain valid canonical types so Android/backend type
# handling stays consistent.
# ------------------------------------------------------------

TYPE_DAILY_REMINDER: Final[str] = (
    "DAILY_REMINDER"
)

TYPE_INACTIVITY_REMINDER: Final[str] = (
    "INACTIVITY_REMINDER"
)


VALID_NOTIFICATION_TYPES: Final[
    frozenset[str]
] = frozenset(
    {
        TYPE_LINK_REQUEST,
        TYPE_LINK_APPROVED,
        TYPE_LINK_DECLINED,
        TYPE_LINK_EXPIRED,
        TYPE_ACCOUNT_UNLINKED,

        TYPE_ALLOWANCE_LOW,
        TYPE_UNUSUAL_SPENDING,
        TYPE_FINANCIAL_RISK,
        TYPE_BUDGET_EXCEEDED,
        TYPE_FORECAST_UPDATE,

        TYPE_STUDENT_ALLOWANCE_LOW,
        TYPE_STUDENT_UNUSUAL_SPENDING,
        TYPE_STUDENT_FINANCIAL_RISK,

        TYPE_DAILY_REMINDER,
        TYPE_INACTIVITY_REMINDER,
    }
)


# ============================================================
# Firebase Initialization
# ============================================================

def initialize_firebase() -> None:
    """
    Initialize Firebase Admin SDK once.

    Local development:
        Uses the Firebase service-account path configured
        by config.py.

    Render:
        FIREBASE_SERVICE_ACCOUNT_PATH should point to the
        Render secret-file location.
    """

    try:
        firebase_admin.get_app()

        logger.debug(
            "Firebase Admin SDK is already initialized."
        )

        return

    except ValueError:
        # No Firebase app exists yet.
        pass

    if not SERVICE_ACCOUNT_PATH.exists():

        raise RuntimeError(
            "Firebase service account file is missing at: "
            f"{SERVICE_ACCOUNT_PATH}"
        )

    try:

        credential = credentials.Certificate(
            str(SERVICE_ACCOUNT_PATH)
        )

        firebase_admin.initialize_app(
            credential
        )

        logger.info(
            "Firebase Admin SDK initialized successfully."
        )

    except Exception as exc:

        logger.exception(
            "Failed to initialize Firebase Admin SDK."
        )

        raise RuntimeError(
            "Failed to initialize Firebase Admin SDK."
        ) from exc


# Initialize Firebase once when module loads.
initialize_firebase()


# ============================================================
# Firestore Client
# ============================================================

def get_firestore_client():
    """
    Return the initialized Firestore client.
    """

    return firestore.client()


# ============================================================
# Notification Type Normalization
# ============================================================

def normalize_notification_type(
    notification_type: str,
) -> str:
    """
    Normalize a notification type into Finora's canonical
    uppercase format.
    """

    if notification_type is None:
        return ""

    return (
        str(notification_type)
        .strip()
        .upper()
    )


# ============================================================
# Notification Type Validation
# ============================================================

def validate_notification_type(
    notification_type: str,
) -> str:
    """
    Normalize and validate a notification type.

    Raises:
        ValueError:
            If the type is empty or unsupported.
    """

    normalized_type = (
        normalize_notification_type(
            notification_type
        )
    )

    if not normalized_type:

        raise ValueError(
            "Notification type is required."
        )

    if (
        normalized_type
        not in VALID_NOTIFICATION_TYPES
    ):

        raise ValueError(
            "Unsupported notification type: "
            f"{normalized_type}"
        )

    return normalized_type


# ============================================================
# Get User FCM Token
# ============================================================

def get_user_fcm_token(
    user_id: str,
) -> str:
    """
    Retrieve the currently registered FCM token for a Finora
    user.

    Finora currently stores one active FCM token per user.
    Therefore the most recently registered compatible device
    receives remote push notifications.

    Raises:
        ValueError:
            If the user does not exist or does not currently
            have an FCM token.
    """

    normalized_user_id = (
        str(user_id or "")
        .strip()
    )

    if not normalized_user_id:

        raise ValueError(
            "Target user ID is required."
        )

    db = get_firestore_client()

    user_reference = (
        db.collection(
            USERS_COLLECTION
        )
        .document(
            normalized_user_id
        )
    )

    user_document = (
        user_reference.get()
    )

    if not user_document.exists:

        raise ValueError(
            "Target user does not exist."
        )

    user_data = (
        user_document.to_dict()
        or {}
    )

    fcm_token = str(
        user_data.get(
            FIELD_FCM_TOKEN
        )
        or ""
    ).strip()

    if not fcm_token:

        raise ValueError(
            "Target user has no FCM token."
        )

    return fcm_token


# ============================================================
# Clear Invalid FCM Token
# ============================================================

def clear_invalid_fcm_token(
    user_id: str,
    invalid_token: str,
) -> None:
    """
    Remove a stale/invalid FCM token from Firestore.

    IMPORTANT:
    The fields are removed only when the currently stored token
    still matches the invalid token.

    This protects a newer token that may have been registered by
    another device while the failed FCM request was in progress.
    """

    normalized_user_id = (
        str(user_id or "")
        .strip()
    )

    normalized_token = (
        str(invalid_token or "")
        .strip()
    )

    if (
        not normalized_user_id
        or not normalized_token
    ):
        return

    try:

        db = get_firestore_client()

        user_reference = (
            db.collection(
                USERS_COLLECTION
            )
            .document(
                normalized_user_id
            )
        )

        @firestore.transactional
        def clear_token_if_unchanged(
            transaction,
        ) -> bool:

            snapshot = (
                user_reference.get(
                    transaction=transaction
                )
            )

            if not snapshot.exists:
                return False

            user_data = (
                snapshot.to_dict()
                or {}
            )

            current_token = str(
                user_data.get(
                    FIELD_FCM_TOKEN
                )
                or ""
            ).strip()

            if (
                current_token
                != normalized_token
            ):
                return False

            transaction.update(
                user_reference,
                {
                    FIELD_FCM_TOKEN:
                        firestore.DELETE_FIELD,

                    FIELD_FCM_TOKEN_UPDATED_AT:
                        firestore.DELETE_FIELD,
                },
            )

            return True

        transaction = (
            db.transaction()
        )

        removed = (
            clear_token_if_unchanged(
                transaction
            )
        )

        if removed:

            logger.info(
                "Removed invalid FCM token for user %s.",
                normalized_user_id,
            )

        else:

            logger.info(
                "Invalid FCM token was not removed because "
                "the stored token had already changed. userId=%s",
                normalized_user_id,
            )

    except Exception:

        # Token cleanup must never hide/replace the original
        # FCM delivery failure.
        logger.exception(
            "Failed to clear invalid FCM token for user %s.",
            normalized_user_id,
        )


# ============================================================
# FCM Push Notification
# ============================================================

def send_push_to_user(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    notification_id: str = "",
    student_id: str = "",
) -> str:
    """
    Send a data-only FCM notification to one Finora user.

    This function ONLY sends the remote push.

    Firestore notification creation is handled separately by
    notification_service.py.

    student_id:
        Empty for the user's own financial notifications.

        Populated for Provider monitoring notifications such as
        STUDENT_ALLOWANCE_LOW so Android knows which linked
        Student should be opened.
    """

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    normalized_user_id = (
        str(user_id or "")
        .strip()
    )

    normalized_title = (
        str(title or "")
        .strip()
    )

    normalized_message = (
        str(message or "")
        .strip()
    )

    normalized_notification_id = (
        str(notification_id or "")
        .strip()
    )

    normalized_student_id = (
        str(student_id or "")
        .strip()
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not normalized_user_id:

        raise ValueError(
            "Target user ID is required."
        )

    normalized_type = (
        validate_notification_type(
            notification_type
        )
    )

    if not normalized_title:

        raise ValueError(
            "Notification title is required."
        )

    if not normalized_message:

        raise ValueError(
            "Notification message is required."
        )

    # --------------------------------------------------------
    # Get FCM Token
    # --------------------------------------------------------

    fcm_token = (
        get_user_fcm_token(
            normalized_user_id
        )
    )

    # --------------------------------------------------------
    # Build FCM Data Payload
    # --------------------------------------------------------

    data = {
        "type":
            normalized_type,

        "title":
            normalized_title,

        "body":
            normalized_message,

        # Android currently accepts both body and message.
        "message":
            normalized_message,

        "notificationId":
            normalized_notification_id,

        "studentId":
            normalized_student_id,
    }

    # --------------------------------------------------------
    # Build Data-Only Message
    # --------------------------------------------------------

    push_message = messaging.Message(
        token=fcm_token,

        data=data,

        android=messaging.AndroidConfig(
            priority="high",
        ),
    )

    # --------------------------------------------------------
    # Send
    # --------------------------------------------------------

    try:

        response = messaging.send(
            push_message
        )

        logger.info(
            "FCM notification sent successfully. "
            "userId=%s type=%s notificationId=%s",
            normalized_user_id,
            normalized_type,
            normalized_notification_id
            or "<none>",
        )

        return response

    except messaging.UnregisteredError as exc:

        logger.warning(
            "Unregistered FCM token detected for user %s.",
            normalized_user_id,
        )

        clear_invalid_fcm_token(
            user_id=normalized_user_id,
            invalid_token=fcm_token,
        )

        raise ValueError(
            "The user's FCM token is no longer valid. "
            "The stored token has been removed and the app "
            "must register a new token."
        ) from exc

    except Exception as exc:

        logger.exception(
            "Failed to send FCM notification. "
            "userId=%s type=%s",
            normalized_user_id,
            normalized_type,
        )

        raise RuntimeError(
            "Failed to send FCM notification."
        ) from exc