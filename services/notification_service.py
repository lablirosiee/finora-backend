import logging

from datetime import (

    datetime,

    timedelta,

    timezone,

)

from typing import (

    Final,

    Optional,

)



from firebase_admin import firestore



from services.fcm_service import (

    TYPE_STUDENT_ALLOWANCE_LOW,

    TYPE_STUDENT_UNUSUAL_SPENDING,

    TYPE_STUDENT_FINANCIAL_RISK,

    TYPE_STUDENT_BUDGET_EXCEEDED,

    TYPE_STUDENT_FORECAST_UPDATE,

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



NOTIFICATIONS_COLLECTION: Final[str] = (

    "notifications"

)






# User-level setting that controls FCM delivery only.
#
# In-app notification history remains independent.
FIELD_PUSH_NOTIFICATIONS_ENABLED: Final[str] = (
    "pushNotificationsEnabled"
)

# ============================================================

# Provider Monitoring Notification Types

#

# These notifications belong to a Provider but concern one

# linked Student.

#

# studentId is required so Android can navigate to the

# correct linked Student monitoring screen.

# ============================================================



STUDENT_MONITORING_TYPES: Final[

    frozenset[str]

] = frozenset(

    {

        TYPE_STUDENT_ALLOWANCE_LOW,

        TYPE_STUDENT_UNUSUAL_SPENDING,

        TYPE_STUDENT_FINANCIAL_RISK,

        TYPE_STUDENT_BUDGET_EXCEEDED,

        TYPE_STUDENT_FORECAST_UPDATE,

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



    return (

        str(

            value or ""

        )

        .strip()

    )





# ============================================================

# Student ID Validation

# ============================================================



def _normalize_student_id(

    notification_type: str,

    student_id: str,

) -> str:

    """

    Normalize studentId.



    Provider-monitoring notification types require a

    studentId.



    Own-finance, linking, and Smart Advice notifications

    do not require studentId.

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

                "monitoring notification type "

                f"{notification_type}."

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

    Create a Firestore notification first and then attempt

    to send the corresponding FCM push.



    Firestore is the source of truth.



    Therefore:



        1. Notification is saved for the notification bell.

        2. FCM push is attempted.

        3. If FCM fails, the Firestore notification remains.



    Supports:



        - Student own-finance notifications

        - Provider own-finance notifications

        - Smart Advice

        - Linking notifications

        - Provider monitoring notifications



    Returns:

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



    user_data = (
        user_snapshot.to_dict()
        or {}
    )

    # Existing users may not have this field yet.
    # Missing means push stays enabled for backward compatibility.
    push_notifications_enabled = (
        user_data.get(
            FIELD_PUSH_NOTIFICATIONS_ENABLED,
            True,
        )
        is not False
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

            "notificationId=%s userId=%s "

            "type=%s studentId=%s",

            notification_id,

            normalized_user_id,

            normalized_type,

            normalized_student_id

            or "\<none>",

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

    # Send FCM Push

    #

    # IMPORTANT:

    #

    # Firestore is intentionally NOT rolled back when FCM

    # delivery fails.

    #

    # This guarantees that the notification remains visible

    # in Finora's notification bell/history.

    # --------------------------------------------------------




    if not push_notifications_enabled:

        logger.info(
            "Notification %s saved for in-app history; "
            "FCM push skipped because push notifications "
            "are disabled for userId=%s.",
            notification_id,
            normalized_user_id,
        )

        return notification_id

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



        # Typical examples:

        # - no registered FCM token

        # - stale/unregistered token

        #

        # Firestore notification remains available.



        logger.warning(

            "Notification %s was saved, but FCM "

            "delivery was unavailable: %s",

            notification_id,

            exc,

        )





    except Exception:



        # Unexpected FCM failure.

        #

        # Firestore notification still remains available.



        logger.exception(

            "Notification %s was saved, but FCM "

            "delivery failed.",

            notification_id,

        )





    return notification_id





# ============================================================

# Check Recent Notification

# ============================================================



def has_recent_notification(

    user_id: str,

    notification_type: str,

    \*,

    student_id: Optional[str] = None,

    within_hours: int = 24,

) -> bool:

    """

    Determine whether an equivalent recent notification

    already exists.



    Deduplication:



        Own-finance / Smart Advice / linking:

            userId + type



        Provider monitoring:

            userId + type + studentId



    The query intentionally filters only by userId and then

    performs remaining checks in Python so Finora does not

    require a Firestore composite index for this operation.

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





    if within_hours <= 0:



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





    try:



        documents = (

            db.collection(

                NOTIFICATIONS_COLLECTION

            )

            .where(

                "userId",

                "==",

                normalized_user_id,

            )

            .limit(

                100

            )

            .stream()

        )





        for document in documents:



            data = (

                document.to_dict()

                or {}

            )





            stored_type = (

                _normalize_text(

                    data.get(

                        "type"

                    )

                )

                .upper()

            )





            if (

                stored_type

                != normalized_type

            ):

                continue





            # ------------------------------------------------

            # Compare Student ID for Provider monitoring

            # ------------------------------------------------



            if normalized_student_id:



                stored_student_id = (

                    _normalize_text(

                        data.get(

                            "studentId"

                        )

                    )

                )





                if (

                    stored_student_id

                    != normalized_student_id

                ):

                    continue





            # ------------------------------------------------

            # Check Creation Timestamp

            # ------------------------------------------------



            created_at = (

                data.get(

                    "createdAt"

                )

            )





            if created_at is None:

                continue





            try:



                if created_at.tzinfo is None:



                    created_at = (

                        created_at.replace(

                            tzinfo=

                                timezone.utc

                        )

                    )





                if created_at >= cutoff:



                    logger.info(

                        "Recent duplicate notification "

                        "found. userId=%s type=%s "

                        "studentId=%s",

                        normalized_user_id,

                        normalized_type,

                        normalized_student_id

                        or "\<none>",

                    )



                    return True





            except (

                AttributeError,

                TypeError,

                ValueError,

            ):



                logger.warning(

                    "Skipping notification %s because "

                    "createdAt is invalid.",

                    document.id,

                )



                continue





        return False





    except Exception as exc:



        logger.exception(

            "Failed to check recent notification. "

            "userId=%s type=%s studentId=%s",

            normalized_user_id,

            normalized_type,

            normalized_student_id

            or "\<none>",

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

    Create a Firestore notification and send its FCM push

    only when an equivalent recent notification does not

    already exist.



    Returns:

        str:

            New notification ID.



        None:

            Equivalent notification already exists.

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





    if within_hours <= 0:



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

            or "\<none>",

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
