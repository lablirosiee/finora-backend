import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from firebase_admin import firestore

from schemas.notification_schemas import (
    NotificationEventRequest,
    NotificationEventResponse,
)

from services.auth_service import (
    AuthenticatedUser,
    get_current_user,
)

from services.notification_service import (
    create_notification_if_not_recent,
)


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Router
# ============================================================

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


# ============================================================
# Firestore Collections
# ============================================================

LINKED_ACCOUNTS_COLLECTION = "linked_accounts"

USERS_COLLECTION = "users"


# ============================================================
# Own-Finance Events
# ============================================================

EVENT_ALLOWANCE_LOW = "ALLOWANCE_LOW"

EVENT_UNUSUAL_SPENDING = "UNUSUAL_SPENDING"

EVENT_FINANCIAL_RISK = "FINANCIAL_RISK"

EVENT_BUDGET_EXCEEDED = "BUDGET_EXCEEDED"

EVENT_FORECAST_UPDATE = "FORECAST_UPDATE"


SUPPORTED_OWN_FINANCE_EVENTS = {
    EVENT_ALLOWANCE_LOW,
    EVENT_UNUSUAL_SPENDING,
    EVENT_FINANCIAL_RISK,
    EVENT_BUDGET_EXCEEDED,
    EVENT_FORECAST_UPDATE,
}


# ============================================================
# Linked-Student Provider Events
# ============================================================

EVENT_STUDENT_ALLOWANCE_LOW = (
    "STUDENT_ALLOWANCE_LOW"
)

EVENT_STUDENT_UNUSUAL_SPENDING = (
    "STUDENT_UNUSUAL_SPENDING"
)

EVENT_STUDENT_FINANCIAL_RISK = (
    "STUDENT_FINANCIAL_RISK"
)

EVENT_STUDENT_BUDGET_EXCEEDED = (
    "STUDENT_BUDGET_EXCEEDED"
)

EVENT_STUDENT_FORECAST_UPDATE = (
    "STUDENT_FORECAST_UPDATE"
)


# ============================================================
# Event Normalization
# ============================================================

def normalize_event_type(
    event_type: str,
) -> str:
    """
    Normalize an Android notification event into
    Finora's canonical uppercase format.
    """

    return (
        str(
            event_type or ""
        )
        .strip()
        .upper()
    )


# ============================================================
# User Name
# ============================================================

def get_user_name(
    user_id: str,
    fallback: str = "The student",
) -> str:
    """
    Retrieve a Finora user's display name.

    This is used only for linked-Provider notification text.
    """

    if not user_id:
        return fallback

    try:

        db = firestore.client()

        snapshot = (
            db.collection(
                USERS_COLLECTION
            )
            .document(
                user_id
            )
            .get()
        )

        if not snapshot.exists:
            return fallback

        data = (
            snapshot.to_dict()
            or {}
        )

        name = (
            str(
                data.get("name")
                or ""
            )
            .strip()
        )

        return (
            name
            if name
            else fallback
        )

    except Exception:

        logger.exception(
            "Unable to retrieve user name. uid=%s",
            user_id,
        )

        return fallback


# ============================================================
# User Role
# ============================================================

def get_user_role(
    user_id: str,
) -> str:
    """
    Retrieve the authenticated Finora user's role from
    Firestore.

    Expected values:
        - student
        - provider

    The value is normalized to lowercase.
    """

    if not user_id:
        return ""

    try:

        db = firestore.client()

        snapshot = (
            db.collection(
                USERS_COLLECTION
            )
            .document(
                user_id
            )
            .get()
        )

        if not snapshot.exists:

            logger.warning(
                "User document does not exist while "
                "resolving role. uid=%s",
                user_id,
            )

            return ""

        data = (
            snapshot.to_dict()
            or {}
        )

        role = (
            str(
                data.get("role")
                or ""
            )
            .strip()
            .lower()
        )

        return role

    except Exception:

        logger.exception(
            "Unable to retrieve user role. uid=%s",
            user_id,
        )

        return ""


# ============================================================
# Get Linked Providers
# ============================================================

def get_linked_provider_ids(
    student_id: str,
) -> list[str]:
    """
    Return the Provider IDs currently linked to a Student.

    Finora stores active Provider-Student relationships in
    the `linked_accounts` collection.

    A link removed through the secure unlink endpoint is
    deleted from that collection, so only existing linked
    account documents are used here.
    """

    if not student_id:
        return []

    db = firestore.client()

    try:

        snapshots = (
            db.collection(
                LINKED_ACCOUNTS_COLLECTION
            )
            .where(
                "studentId",
                "==",
                student_id,
            )
            .stream()
        )

        provider_ids: list[str] = []

        for snapshot in snapshots:

            data = (
                snapshot.to_dict()
                or {}
            )

            provider_id = (
                str(
                    data.get(
                        "providerId"
                    )
                    or ""
                )
                .strip()
            )

            if (
                provider_id
                and provider_id
                not in provider_ids
            ):

                provider_ids.append(
                    provider_id
                )

        return provider_ids

    except Exception:

        logger.exception(
            "Failed to retrieve linked Providers "
            "for student=%s.",
            student_id,
        )

        return []


# ============================================================
# Provider Fan-Out
# ============================================================

def notify_linked_providers(
    student_id: str,
    own_event_type: str,
) -> int:
    """
    Send the appropriate financial monitoring notification
    to every Provider currently linked to the Student.

    IMPORTANT:

    The Student never supplies a Provider UID.

    Provider recipients are determined entirely by the
    backend using the verified `linked_accounts` collection.

    Returns the number of newly created Provider
    notifications.
    """

    provider_ids = (
        get_linked_provider_ids(
            student_id
        )
    )

    if not provider_ids:

        logger.info(
            "No linked Providers found for student=%s.",
            student_id,
        )

        return 0


    student_name = (
        get_user_name(
            student_id,
            "The student",
        )
    )


    # --------------------------------------------------------
    # Provider Notification Content
    # --------------------------------------------------------

    if (
        own_event_type
        == EVENT_ALLOWANCE_LOW
    ):

        provider_event_type = (
            EVENT_STUDENT_ALLOWANCE_LOW
        )

        title = (
            "Student Allowance Running Low"
        )

        message = (
            f"{student_name}'s remaining allowance "
            "is running low."
        )

        within_hours = 24


    elif (
        own_event_type
        == EVENT_UNUSUAL_SPENDING
    ):

        provider_event_type = (
            EVENT_STUDENT_UNUSUAL_SPENDING
        )

        title = (
            "Unusual Student Spending"
        )

        message = (
            f"{student_name}'s recent spending "
            "is higher than usual."
        )

        within_hours = 24


    elif (
        own_event_type
        == EVENT_FINANCIAL_RISK
    ):

        provider_event_type = (
            EVENT_STUDENT_FINANCIAL_RISK
        )

        title = (
            "Student Financial Risk"
        )

        message = (
            f"{student_name}'s current spending "
            "pattern may put the allowance at risk."
        )

        within_hours = 24


    elif (
        own_event_type
        == EVENT_BUDGET_EXCEEDED
    ):

        provider_event_type = (
            EVENT_STUDENT_BUDGET_EXCEEDED
        )

        title = (
            "Student Budget Exceeded"
        )

        message = (
            f"{student_name} has exceeded the "
            "current allowance budget."
        )

        within_hours = 24


    elif (
        own_event_type
        == EVENT_FORECAST_UPDATE
    ):

        provider_event_type = (
            EVENT_STUDENT_FORECAST_UPDATE
        )

        title = (
            "Student Forecast Updated"
        )

        message = (
            f"{student_name}'s allowance forecast "
            "has been updated."
        )

        within_hours = 12


    else:

        logger.warning(
            "Provider fan-out skipped for unsupported "
            "event. student=%s event=%s",
            student_id,
            own_event_type,
        )

        return 0


    # --------------------------------------------------------
    # Send to Each Linked Provider
    # --------------------------------------------------------

    created_count = 0

    for provider_id in provider_ids:

        try:

            notification_id = (
                create_notification_if_not_recent(
                    user_id=
                        provider_id,

                    notification_type=
                        provider_event_type,

                    title=
                        title,

                    message=
                        message,

                    student_id=
                        student_id,

                    within_hours=
                        within_hours,
                )
            )

            if (
                notification_id
                is not None
            ):

                created_count += 1

                logger.info(
                    "Linked-Provider notification created. "
                    "provider=%s student=%s type=%s "
                    "notificationId=%s",
                    provider_id,
                    student_id,
                    provider_event_type,
                    notification_id,
                )

            else:

                logger.info(
                    "Linked-Provider notification skipped "
                    "because a recent equivalent exists. "
                    "provider=%s student=%s type=%s",
                    provider_id,
                    student_id,
                    provider_event_type,
                )

        except Exception:

            # One Provider notification failure must not
            # prevent the Student's own notification or
            # notifications to other linked Providers.

            logger.exception(
                "Failed to create linked-Provider "
                "notification. provider=%s student=%s "
                "type=%s",
                provider_id,
                student_id,
                provider_event_type,
            )

    return created_count


# ============================================================
# Production Own-Finance Notification Endpoint
# ============================================================

@router.post(
    "/event",
    response_model=NotificationEventResponse,
    status_code=status.HTTP_200_OK,
)
def trigger_notification_event(
    request: NotificationEventRequest,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
) -> NotificationEventResponse:
    """
    Handle an authenticated Finora user's financial
    notification event.

    SECURITY:

    - The own-account recipient is always current_user.uid.
    - Android cannot choose another user's UID.
    - Linked Provider recipients are resolved entirely by
      the backend from Firestore.
    - A Provider receives a Student financial notification
      only when a linked_accounts document exists.
    """

    # --------------------------------------------------------
    # Normalize Event
    # --------------------------------------------------------

    event_type = (
        normalize_event_type(
            request.eventType
        )
    )


    # --------------------------------------------------------
    # Validate Event
    # --------------------------------------------------------

    if (
        event_type
        not in SUPPORTED_OWN_FINANCE_EVENTS
    ):

        logger.warning(
            "Unsupported own-finance notification event. "
            "uid=%s eventType=%s",
            current_user.uid,
            event_type,
        )

        raise HTTPException(
            status_code=
                status.HTTP_400_BAD_REQUEST,

            detail=(
                "Unsupported own-finance "
                "notification event."
            ),
        )


    # ========================================================
    # LOW ALLOWANCE
    # ========================================================

    if (
        event_type
        == EVENT_ALLOWANCE_LOW
    ):

        notification_id = (
            create_notification_if_not_recent(
                user_id=
                    current_user.uid,

                notification_type=
                    EVENT_ALLOWANCE_LOW,

                title=
                    "Low Allowance",

                message=(
                    "Your remaining allowance is "
                    "running low."
                ),

                within_hours=
                    24,
            )
        )


    # ========================================================
    # UNUSUAL SPENDING
    # ========================================================

    elif (
        event_type
        == EVENT_UNUSUAL_SPENDING
    ):

        notification_id = (
            create_notification_if_not_recent(
                user_id=
                    current_user.uid,

                notification_type=
                    EVENT_UNUSUAL_SPENDING,

                title=
                    "Unusual Spending Detected",

                message=(
                    "Your recent spending is higher "
                    "than usual."
                ),

                within_hours=
                    24,
            )
        )


    # ========================================================
    # FINANCIAL RISK
    # ========================================================

    elif (
        event_type
        == EVENT_FINANCIAL_RISK
    ):

        notification_id = (
            create_notification_if_not_recent(
                user_id=
                    current_user.uid,

                notification_type=
                    EVENT_FINANCIAL_RISK,

                title=
                    "Financial Risk Alert",

                message=(
                    "Your current spending pattern may "
                    "put your allowance at risk."
                ),

                within_hours=
                    24,
            )
        )


    # ========================================================
    # BUDGET EXCEEDED
    # ========================================================

    elif (
        event_type
        == EVENT_BUDGET_EXCEEDED
    ):

        notification_id = (
            create_notification_if_not_recent(
                user_id=
                    current_user.uid,

                notification_type=
                    EVENT_BUDGET_EXCEEDED,

                title=
                    "Budget Exceeded",

                message=(
                    "You have exceeded your current "
                    "allowance budget."
                ),

                within_hours=
                    24,
            )
        )


    # ========================================================
    # FORECAST UPDATED
    # ========================================================

    elif (
        event_type
        == EVENT_FORECAST_UPDATE
    ):

        notification_id = (
            create_notification_if_not_recent(
                user_id=
                    current_user.uid,

                notification_type=
                    EVENT_FORECAST_UPDATE,

                title=
                    "Forecast Updated",

                message=(
                    "Your allowance forecast has been "
                    "updated."
                ),

                within_hours=
                    12,
            )
        )


    # ========================================================
    # DEFENSIVE FALLBACK
    # ========================================================

    else:

        raise HTTPException(
            status_code=
                status.HTTP_400_BAD_REQUEST,

            detail=(
                "Unsupported notification event."
            ),
        )


    # ========================================================
    # LINKED PROVIDER FAN-OUT
    # ========================================================

    provider_notifications_created = 0

    try:

        user_role = (
            get_user_role(
                current_user.uid
            )
        )

        logger.info(
            "Notification owner role resolved. "
            "uid=%s role=%s",
            current_user.uid,
            user_role or "UNKNOWN",
        )


        # ----------------------------------------------------
        # Student -> Linked Provider(s)
        # ----------------------------------------------------
        #
        # Only Student financial events are forwarded to
        # linked Providers.
        #
        # A Provider's own financial events stay with that
        # Provider and are not forwarded.
        # ----------------------------------------------------

        if user_role == "student":

            provider_notifications_created = (
                notify_linked_providers(
                    student_id=
                        current_user.uid,

                    own_event_type=
                        event_type,
                )
            )

            logger.info(
                "Student Provider fan-out completed. "
                "student=%s event=%s "
                "providerNotificationsCreated=%d",
                current_user.uid,
                event_type,
                provider_notifications_created,
            )


        elif user_role == "provider":

            logger.info(
                "Provider own-finance event. "
                "Linked-Provider fan-out not required. "
                "uid=%s event=%s",
                current_user.uid,
                event_type,
            )


        else:

            logger.warning(
                "Unknown or missing Finora user role. "
                "Own notification was processed, but "
                "Provider fan-out was skipped. "
                "uid=%s role=%s event=%s",
                current_user.uid,
                user_role or "UNKNOWN",
                event_type,
            )


    except Exception:

        # A Provider fan-out failure must never cause the
        # authenticated user's own notification request to
        # fail.

        logger.exception(
            "Linked-Provider fan-out processing failed. "
            "uid=%s event=%s",
            current_user.uid,
            event_type,
        )


    # ========================================================
    # RESPONSE
    # ========================================================

    if notification_id is None:

        logger.info(
            "Own notification skipped because a recent "
            "equivalent notification already exists. "
            "uid=%s event=%s "
            "providerNotificationsCreated=%d",
            current_user.uid,
            event_type,
            provider_notifications_created,
        )

        return NotificationEventResponse(
            success=True,
            notificationId=None,
            skipped=True,
            message=(
                "A recent equivalent notification "
                "already exists."
            ),
        )


    logger.info(
        "Own notification event completed successfully. "
        "uid=%s event=%s notificationId=%s "
        "providerNotificationsCreated=%d",
        current_user.uid,
        event_type,
        notification_id,
        provider_notifications_created,
    )

    return NotificationEventResponse(
        success=True,
        notificationId=notification_id,
        skipped=False,
        message=(
            "Notification created successfully."
        ),
    )