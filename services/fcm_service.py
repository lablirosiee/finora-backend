import logging
import os
from typing import Final

import firebase_admin
from firebase_admin import credentials, firestore, messaging


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Firebase Configuration
# ============================================================

SERVICE_ACCOUNT_PATH: Final[str] = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_PATH",
    "/etc/secrets/firebase-service-account.json",
).strip()


# ============================================================
# Firestore Collections / Fields
# ============================================================

USERS_COLLECTION: Final[str] = "users"

FIELD_FCM_TOKEN: Final[str] = "fcmToken"
FIELD_FCM_TOKEN_UPDATED_AT: Final[str] = "fcmTokenUpdatedAt"


# ============================================================
# Canonical Notification Types
#
# IMPORTANT:
# These must stay aligned with NotificationHelper.kt.
# ============================================================

TYPE_LINK_REQUEST: Final[str] = "LINK_REQUEST"
TYPE_LINK_APPROVED: Final[str] = "LINK_APPROVED"
TYPE_LINK_DECLINED: Final[str] = "LINK_DECLINED"
TYPE_LINK_EXPIRED: Final[str] = "LINK_EXPIRED"
TYPE_ACCOUNT_UNLINKED: Final[str] = "ACCOUNT_UNLINKED"

TYPE_ALLOWANCE_LOW: Final[str] = "ALLOWANCE_LOW"
TYPE_UNUSUAL_SPENDING: Final[str] = "UNUSUAL_SPENDING"
TYPE_FINANCIAL_RISK: Final[str] = "FINANCIAL_RISK"
TYPE_BUDGET_EXCEEDED: Final[str] = "BUDGET_EXCEEDED"
TYPE_FORECAST_UPDATE: Final[str] = "FORECAST_UPDATE"

TYPE_STUDENT_ALLOWANCE_LOW: Final[str] = (
    "STUDENT_ALLOWANCE_LOW"
)

TYPE_STUDENT_UNUSUAL_SPENDING: Final[str] = (
    "STUDENT_UNUSUAL_SPENDING"
)

TYPE_STUDENT_FINANCIAL_RISK: Final[str] = (
    "STUDENT_FINANCIAL_RISK"
)

TYPE_DAILY_REMINDER: Final[str] = "DAILY_REMINDER"
TYPE_INACTIVITY_REMINDER: Final[str] = "INACTIVITY_REMINDER"


VALID_NOTIFICATION_TYPES: Final[frozenset[str]] = frozenset(
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

    On Render, the service account file should normally be:
    /etc/secrets/firebase-service-account.json
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


    if not SERVICE_ACCOUNT_PATH:

        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_PATH is not configured."
        )


    if not os.path.isfile(
        SERVICE_ACCOUNT_PATH
    ):

        raise RuntimeError(
            "Firebase service account file is missing at: "
            f"{SERVICE_ACCOUNT_PATH}"
        )


    try:

        credential = credentials.Certificate(
            SERVICE_ACCOUNT_PATH
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


# Initialize Firebase when this module loads.
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
    Normalize a notification type into the canonical format
    used by both the backend and Android application.
    """

    return (
        notification_type
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
    Normalize and validate the notification type.

    Returns:
        The normalized canonical notification type.

    Raises:
        ValueError:
            If the type is empty or unsupported.
    """

    normalized_type = normalize_notification_type(
        notification_type
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
    Retrieve the current FCM token for a Finora user.

    Raises:
        ValueError:
            If the user does not exist or has no registered
            FCM token.
    """

    normalized_user_id = (
        user_id.strip()
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
    Clear a stale FCM token from Firestore.

    The token is cleared only if the user's currently stored
    token still matches the invalid token.

    This prevents accidentally deleting a newer token that may
    have been registered while the push was being processed.
    """

    normalized_user_id = (
        user_id.strip()
    )

    normalized_token = (
        invalid_token.strip()
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
        ) -> None:

            snapshot = (
                user_reference.get(
                    transaction=transaction
                )
            )


            if not snapshot.exists:
                return


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
                return


            transaction.update(
                user_reference,
                {
                    FIELD_FCM_TOKEN: "",
                    FIELD_FCM_TOKEN_UPDATED_AT:
                        firestore.SERVER_TIMESTAMP,
                },
            )


        transaction = (
            db.transaction()
        )


        clear_token_if_unchanged(
            transaction
        )


        logger.info(
            "Cleared invalid FCM token for user %s.",
            normalized_user_id,
        )

    except Exception:

        
         #Token cleanup must never cause the original push
         #operation to fail differently.
         
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

    This function ONLY sends the push notification.

    It does not create the Firestore notification document.
    Production notification creation will be handled by the
    notification service before this function is called.
    """

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    normalized_user_id = (
        user_id.strip()
    )

    normalized_title = (
        title.strip()
    )

    normalized_message = (
        message.strip()
    )

    normalized_notification_id = (
        notification_id.strip()
    )

    normalized_student_id = (
        student_id.strip()
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

    
         # Keep "message" temporarily for compatibility with
         # the Android receiver, which currently supports both
         #"body" and "message".
         
        "message":
            normalized_message,

        "notificationId":
            normalized_notification_id,

        "studentId":
            normalized_student_id,
    }


    # --------------------------------------------------------
    # Build Data-Only FCM Message
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
            "The stored token has been cleared and the app "
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