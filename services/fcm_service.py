import logging
from typing import Final

import firebase_admin
from firebase_admin import (
    credentials,
    firestore,
    messaging,
)

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
# Keep these aligned with Android notification handling.
# ============================================================

# ------------------------------------------------------------
# Linking Notifications
# ------------------------------------------------------------

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
# Own Financial Notifications
#
# These can belong to either Student or Provider.
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
# Smart Advice
#
# Smart Advice belongs to the user whose financial behavior
# generated the advice.
# ------------------------------------------------------------

TYPE_SMART_ADVICE: Final[str] = (
    "SMART_ADVICE"
)


# ------------------------------------------------------------
# Provider Monitoring Notifications
#
# These concern one linked Student.
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

TYPE_STUDENT_BUDGET_EXCEEDED: Final[str] = (
    "STUDENT_BUDGET_EXCEEDED"
)

TYPE_STUDENT_FORECAST_UPDATE: Final[str] = (
    "STUDENT_FORECAST_UPDATE"
)


# ------------------------------------------------------------
# Local Reminder Types
#
# Android currently creates these locally through WorkManager.
# ------------------------------------------------------------

TYPE_DAILY_REMINDER: Final[str] = (
    "DAILY_REMINDER"
)

TYPE_INACTIVITY_REMINDER: Final[str] = (
    "INACTIVITY_REMINDER"
)


# ============================================================
# Valid Notification Types
# ============================================================

VALID_NOTIFICATION_TYPES: Final[
    frozenset[str]
] = frozenset(
    {
        # Linking
        TYPE_LINK_REQUEST,
        TYPE_LINK_APPROVED,
        TYPE_LINK_DECLINED,
        TYPE_LINK_EXPIRED,
        TYPE_ACCOUNT_UNLINKED,

        # Own finances
        TYPE_ALLOWANCE_LOW,
        TYPE_UNUSUAL_SPENDING,
        TYPE_FINANCIAL_RISK,
        TYPE_BUDGET_EXCEEDED,
        TYPE_FORECAST_UPDATE,

        # Smart Advice
        TYPE_SMART_ADVICE,

        # Linked Student -> Provider
        TYPE_STUDENT_ALLOWANCE_LOW,
        TYPE_STUDENT_UNUSUAL_SPENDING,
        TYPE_STUDENT_FINANCIAL_RISK,
        TYPE_STUDENT_BUDGET_EXCEEDED,
        TYPE_STUDENT_FORECAST_UPDATE,

        # Local Android reminders
        TYPE_DAILY_REMINDER,
        TYPE_INACTIVITY_REMINDER,
    }
)


# ============================================================
# Firebase Initialization
# ============================================================

def initialize_firebase() -> None:
    """
    Initialize Firebase Admin SDK exactly once.
    """

    try:

        firebase_admin.get_app()

        logger.debug(
            "Firebase Admin SDK is already initialized."
        )

        return

    except ValueError:

        # Firebase has not been initialized yet.
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


# Initialize Firebase once when this module loads.
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
    Normalize and validate a Finora notification type.
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
    Retrieve the currently registered FCM token for a user.

    Finora currently stores one active FCM token per user.
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

    fcm_token = (
        str(
            user_data.get(
                FIELD_FCM_TOKEN
            )
            or ""
        )
        .strip()
    )

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
    Remove an invalid/stale token only if the token currently
    stored in Firestore still matches the failed token.
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

            current_token = (
                str(
                    user_data.get(
                        FIELD_FCM_TOKEN
                    )
                    or ""
                )
                .strip()
            )


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
                "the stored token had already changed. "
                "userId=%s",
                normalized_user_id,
            )


    except Exception:

        # Token cleanup should never hide the original
        # FCM delivery error.

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
    Send one data-only FCM push to a Finora user.

    Firestore notification creation is handled by
    notification_service.py.

    student_id is populated for Provider monitoring
    notifications so Android knows which Student the
    notification concerns.
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
    # Retrieve FCM Token
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

        # Android accepts both body and message.
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