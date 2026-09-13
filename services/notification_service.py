import logging
from datetime import datetime, timedelta, timezone
from typing import Final, Optional

from firebase_admin import firestore

from services.fcm_service import (
    TYPE_STUDENT_ALLOWANCE_LOW,
    TYPE_STUDENT_FINANCIAL_RISK,
    TYPE_STUDENT_UNUSUAL_SPENDING,
    send_push_to_user,
    validate_notification_type,
)


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Firestore Configuration
# ============================================================

USERS_COLLECTION: Final[str] = "users"

NOTIFICATIONS_COLLECTION: Final[str] = "notifications"


# ============================================================
# Provider Monitoring Notification Types
#
# These notification types are specifically sent to a Provider
# about one linked Student.
#
# studentId is required for these types so Android can navigate
# to the correct linked Student monitoring screen.
# ============================================================

STUDENT_MONITORING_TYPES: Final[frozenset[str]] = frozenset(
    {
        TYPE_STUDENT_ALLOWANCE_LOW,
        TYPE_STUDENT_UNUSUAL_SPENDING,
        TYPE_STUDENT_FINANCIAL_RISK,
    }
)


# ============================================================
# Text Normalization Helper
# ============================================================

def _normalize_text(
    value: object,
) -> str:
    """
    Convert an optional value into a safe trimmed string.
    """

    return str(
        value or ""
    ).strip()


# ============================================================
# Student ID Validation
# ============================================================

def _normalize_student_id(
    notification_type: str,
    student_id: str,
) -> str:
    """
    Normalize studentId.

    Provider monitoring notification types require studentId.

    Examples:
        STUDENT_ALLOWANCE_LOW
        STUDENT_UNUSUAL_SPENDING
        STUDENT_FINANCIAL_RISK

    Own-finance notification types do not require studentId.

    Examples:
        ALLOWANCE_LOW
        UNUSUAL_SPENDING
        FINANCIAL_RISK
        BUDGET_EXCEEDED
        FORECAST_UPDATE
    """

    normalized_student_id = (
        _normalize_text(
            student_id
        )
    )

    if (
        notification_type
        in STUDENT_MONITORING_TYPES
    ):

        if not normalized_student_id:

            raise ValueError(
                "studentId is required for provider-side "
                f"monitoring notification type {notification_type}."
            )

    return normalized_student_id


# ============================================================
# Create Firestore Notification + Send FCM
# ============================================================

def create_and_send_notification(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    student_id: str = "",
) -> str:
    """
    Create a Firestore notification first, then attempt to send
    its corresponding data-only FCM push.

    Firestore remains the source of truth.

    If FCM delivery fails, the Firestore notification remains
    available in the user's Notifications screen.

    This function supports:
        - Student own-finance notifications
        - Provider own-finance notifications
        - Linking notifications
        - Provider monitoring notifications

    Returns:
        str:
            Firestore notification document ID.
    """

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    normalized_user_id = (
        _normalize_text(
            user_id
        )
    )

    normalized_type = (
        validate_notification_type(
            notification_type
        )
    )

    normalized_title = (
        _normalize_text(
            title
        )
    )

    normalized_message = (
        _normalize_text(
            message
        )
    )

    normalized_student_id = (
        _normalize_student_id(
            notification_type=
                normalized_type,
            student_id=
                student_id,
        )
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not normalized_user_id:

        raise ValueError(
            "Target user ID is required."
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
    # Firestore Client
    # --------------------------------------------------------

    db = firestore.client()

    # --------------------------------------------------------
    # Verify Target User Exists
    # --------------------------------------------------------

    user_reference = (
        db.collection(
            USERS_COLLECTION
        )
        .document(
            normalized_user_id
        )
    )

    user_snapshot = (
        user_reference.get()
    )

    if not user_snapshot.exists:

        raise ValueError(
            "Target user does not exist."
        )

    # --------------------------------------------------------
    # Create Notification Document
    # --------------------------------------------------------

    notification_reference = (
        db.collection(
            NOTIFICATIONS_COLLECTION
        )
        .document()
    )

    notification_id = (
        notification_reference.id
    )

    notification_data = {
        "id":
            notification_id,

        "userId":
            normalized_user_id,

        "title":
            normalized_title,

        "message":
            normalized_message,

        "type":
            normalized_type,

        "studentId":
            (
                normalized_student_id
                if normalized_student_id
                else None
            ),

        "createdAt":
            firestore.SERVER_TIMESTAMP,

        "read":
            False,
    }

    try:

        notification_reference.set(
            notification_data
        )

        logger.info(
            "Notification created. "
            "notificationId=%s userId=%s type=%s studentId=%s",
            notification_id,
            normalized_user_id,
            normalized_type,
            normalized_student_id
            or "<none>",
        )

    except Exception as exc:

        logger.exception(
            "Failed to create Firestore notification. "
            "userId=%s type=%s",
            normalized_user_id,
            normalized_type,
        )

        raise RuntimeError(
            "Failed to create notification."
        ) from exc

    # --------------------------------------------------------
    # Send FCM
    #
    # IMPORTANT:
    # The Firestore document is intentionally NOT deleted when
    # FCM fails.
    #
    # This allows the notification to remain visible inside
    # Finora's Notifications screen even when push delivery is
    # unavailable.
    # --------------------------------------------------------

    try:

        send_push_to_user(
            user_id=
                normalized_user_id,

            notification_type=
                normalized_type,

            title=
                normalized_title,

            message=
                normalized_message,

            notification_id=
                notification_id,

            student_id=
                normalized_student_id,
        )

        logger.info(
            "FCM push sent for notification %s.",
            notification_id,
        )

    except ValueError as exc:

        # Examples:
        # - user has no registered FCM token
        # - user's token is stale or unregistered
        #
        # Firestore notification remains available.

        logger.warning(
            "Notification %s was saved, but FCM delivery "
            "was unavailable: %s",
            notification_id,
            exc,
        )

    except Exception:

        # Unexpected FCM failure.
        #
        # Firestore notification still remains available.

        logger.exception(
            "Notification %s was saved, but FCM delivery "
            "failed.",
            notification_id,
        )

    return notification_id


# ============================================================
# Check Recent Notification
# ============================================================

def has_recent_notification(
    user_id: str,
    notification_type: str,
    *,
    student_id: Optional[str] = None,
    within_hours: int = 24,
) -> bool:
    """
    Check whether an equivalent notification already exists
    within the specified number of hours.

    This prevents repeated notifications when financial data is
    recalculated several times.

    Own-finance deduplication:
        userId + type

    Provider-monitoring deduplication:
        provider userId + type + studentId
    """

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    normalized_user_id = (
        _normalize_text(
            user_id
        )
    )

    normalized_type = (
        validate_notification_type(
            notification_type
        )
    )

    normalized_student_id = (
        _normalize_text(
            student_id
        )
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not normalized_user_id:

        raise ValueError(
            "Target user ID is required."
        )

    if (
        within_hours <= 0
    ):

        raise ValueError(
            "within_hours must be greater than zero."
        )

    if (
        normalized_type
        in STUDENT_MONITORING_TYPES
        and not normalized_student_id
    ):

        raise ValueError(
            "studentId is required when checking a "
            "provider-side monitoring notification."
        )

    # --------------------------------------------------------
    # Calculate Cutoff
    # --------------------------------------------------------

    cutoff = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            hours=within_hours
        )
    )

    # --------------------------------------------------------
    # Firestore Query
    # --------------------------------------------------------

    db = firestore.client()

    query = (
        db.collection(
            NOTIFICATIONS_COLLECTION
        )
        .where(
            "userId",
            "==",
            normalized_user_id,
        )
        .where(
            "type",
            "==",
            normalized_type,
        )
        .where(
            "createdAt",
            ">=",
            cutoff,
        )
    )

    # Provider monitoring deduplication must be specific
    # to the linked Student.

    if normalized_student_id:

        query = query.where(
            "studentId",
            "==",
            normalized_student_id,
        )

    try:

        documents = (
            query
            .limit(1)
            .stream()
        )

        return (
            next(
                documents,
                None,
            )
            is not None
        )

    except Exception as exc:

        logger.exception(
            "Failed to check recent notification. "
            "userId=%s type=%s studentId=%s",
            normalized_user_id,
            normalized_type,
            normalized_student_id
            or "<none>",
        )

        raise RuntimeError(
            "Failed to check recent notification."
        ) from exc


# ============================================================
# Create Notification If Not Recent
# ============================================================

def create_notification_if_not_recent(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    student_id: str = "",
    within_hours: int = 24,
) -> Optional[str]:
    """
    Create and send a notification only if an equivalent one
    does not already exist within the specified period.

    Returns:
        str:
            New notification ID when a notification is created.

        None:
            Notification was skipped because an equivalent
            notification already exists.
    """

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    normalized_user_id = (
        _normalize_text(
            user_id
        )
    )

    normalized_type = (
        validate_notification_type(
            notification_type
        )
    )

    normalized_title = (
        _normalize_text(
            title
        )
    )

    normalized_message = (
        _normalize_text(
            message
        )
    )

    normalized_student_id = (
        _normalize_student_id(
            notification_type=
                normalized_type,
            student_id=
                student_id,
        )
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not normalized_user_id:

        raise ValueError(
            "Target user ID is required."
        )

    if not normalized_title:

        raise ValueError(
            "Notification title is required."
        )

    if not normalized_message:

        raise ValueError(
            "Notification message is required."
        )

    if (
        within_hours <= 0
    ):

        raise ValueError(
            "within_hours must be greater than zero."
        )

    # --------------------------------------------------------
    # Check Existing Notification
    # --------------------------------------------------------

    already_exists = (
        has_recent_notification(
            user_id=
                normalized_user_id,

            notification_type=
                normalized_type,

            student_id=
                (
                    normalized_student_id
                    if normalized_student_id
                    else None
                ),

            within_hours=
                within_hours,
        )
    )

    if already_exists:

        logger.info(
            "Duplicate notification skipped. "
            "userId=%s type=%s studentId=%s",
            normalized_user_id,
            normalized_type,
            normalized_student_id
            or "<none>",
        )

        return None

    # --------------------------------------------------------
    # Create Firestore Notification + Send FCM
    # --------------------------------------------------------

    return create_and_send_notification(
        user_id=
            normalized_user_id,

        notification_type=
            normalized_type,

        title=
            normalized_title,

        message=
            normalized_message,

        student_id=
            normalized_student_id,
    )