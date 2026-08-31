import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from firebase_admin import firestore

from services.fcm_service import (
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

USERS_COLLECTION = "users"
NOTIFICATIONS_COLLECTION = "notifications"


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
    Create a notification document in Firestore first,
    then send the corresponding data-only FCM push.

    Firestore is the source of truth.

    If FCM delivery fails, the Firestore notification remains
    available in the user's Notifications screen.

    Returns:
        Firestore notification document ID.
    """

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    normalized_user_id = user_id.strip()

    normalized_type = validate_notification_type(
        notification_type
    )

    normalized_title = title.strip()

    normalized_message = message.strip()

    normalized_student_id = student_id.strip()


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
    # Firestore
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
        "id": notification_id,
        "userId": normalized_user_id,
        "title": normalized_title,
        "message": normalized_message,
        "type": normalized_type,
        "studentId": (
            normalized_student_id
            if normalized_student_id
            else None
        ),
        "createdAt": firestore.SERVER_TIMESTAMP,
        "isRead": False,
    }


    try:

        notification_reference.set(
            notification_data
        )

        logger.info(
            "Notification created. "
            "notificationId=%s userId=%s type=%s",
            notification_id,
            normalized_user_id,
            normalized_type,
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
    # --------------------------------------------------------
    #
    # Do not delete the Firestore document when FCM fails.
    #
    # The notification must still appear when the user opens
    # the Notifications screen.
    # --------------------------------------------------------

    try:

        send_push_to_user(
            user_id=normalized_user_id,
            notification_type=normalized_type,
            title=normalized_title,
            message=normalized_message,
            notification_id=notification_id,
            student_id=normalized_student_id,
        )

        logger.info(
            "FCM push sent for notification %s.",
            notification_id,
        )

    except ValueError as exc:

        # Examples:
        # - user has no current FCM token
        # - user's stored token became invalid
        #
        # The Firestore notification still exists.

        logger.warning(
            "Notification %s was saved, but FCM delivery "
            "was unavailable: %s",
            notification_id,
            exc,
        )

    except Exception:

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
    Check whether a similar notification was already created
    recently.

    This helps prevent repeated financial notifications every
    time an expense or forecast is recalculated.
    """

    # --------------------------------------------------------
    # Normalize / Validate
    # --------------------------------------------------------

    normalized_user_id = user_id.strip()

    normalized_type = validate_notification_type(
        notification_type
    )

    normalized_student_id = (
        student_id.strip()
        if student_id
        else ""
    )


    if not normalized_user_id:
        raise ValueError(
            "Target user ID is required."
        )

    if within_hours <= 0:
        raise ValueError(
            "within_hours must be greater than zero."
        )


    # --------------------------------------------------------
    # Calculate Cutoff
    # --------------------------------------------------------

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(
            hours=within_hours
        )
    )


    # --------------------------------------------------------
    # Build Firestore Query
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


    # For provider-side notifications, studentId makes
    # deduplication specific to that particular student.

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

        return next(
            documents,
            None,
        ) is not None

    except Exception as exc:

        logger.exception(
            "Failed to check recent notification. "
            "userId=%s type=%s studentId=%s",
            normalized_user_id,
            normalized_type,
            normalized_student_id or "<none>",
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
    Create and send a notification only when another equivalent
    notification has not been created within the specified
    period.

    Returns:
        str:
            New notification ID when created.

        None:
            Notification was skipped because a recent matching
            notification already exists.
    """

    normalized_user_id = (
        user_id.strip()
    )

    normalized_student_id = (
        student_id.strip()
    )

    normalized_type = (
        validate_notification_type(
            notification_type
        )
    )


    if not normalized_user_id:
        raise ValueError(
            "Target user ID is required."
        )


    # --------------------------------------------------------
    # Check Existing Alert
    # --------------------------------------------------------

    already_exists = has_recent_notification(
        user_id=normalized_user_id,
        notification_type=normalized_type,
        student_id=(
            normalized_student_id
            if normalized_student_id
            else None
        ),
        within_hours=within_hours,
    )


    if already_exists:

        logger.info(
            "Duplicate notification skipped. "
            "userId=%s type=%s studentId=%s",
            normalized_user_id,
            normalized_type,
            normalized_student_id or "<none>",
        )

        return None


    # --------------------------------------------------------
    # Create + Send
    # --------------------------------------------------------

    return create_and_send_notification(
        user_id=normalized_user_id,
        notification_type=normalized_type,
        title=title,
        message=message,
        student_id=normalized_student_id,
    )