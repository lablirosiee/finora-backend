import logging

from fastapi import (

    APIRouter,

    Depends,

    HTTPException,

    status,

)

from firebase_admin import firestore

from schemas.link_schemas import (

    LinkNotificationRequest,

    LinkNotificationResponse,

    UnlinkAccountsRequest,

    UnlinkAccountsResponse,

)

from services.auth_service import (

    AuthenticatedUser,

    get_current_user,

)

from services.notification_service import (

    create_and_send_notification,


)





# ============================================================

# Logging

# ============================================================



logger = logging.getLogger(__name__)





# ============================================================

# Router

# ============================================================



router = APIRouter(

    prefix="/links",

    tags=["Links"],

)





# ============================================================

# Collections

# ============================================================



LINK_REQUESTS_COLLECTION = "link_requests"

LINKED_ACCOUNTS_COLLECTION = "linked_accounts"

USERS_COLLECTION = "users"





# ============================================================

# Supported Link Notification Events

# ============================================================



EVENT_LINK_REQUEST = "LINK_REQUEST"

EVENT_LINK_APPROVED = "LINK_APPROVED"

EVENT_LINK_DECLINED = "LINK_DECLINED"

EVENT_LINK_EXPIRED = "LINK_EXPIRED"



EVENT_ACCOUNT_UNLINKED = "ACCOUNT_UNLINKED"





SUPPORTED_LINK_EVENTS = {

    EVENT_LINK_REQUEST,

    EVENT_LINK_APPROVED,

    EVENT_LINK_DECLINED,

    EVENT_LINK_EXPIRED,

}





# ============================================================

# Helpers

# ============================================================



def normalize_event_type(

    event_type: str,

) -> str:

    """

    Normalize an incoming link-event type.

    """



    return (

        str(

            event_type or ""

        )

        .strip()

        .upper()

    )





def get_link_request(

    request_id: str,

) -> dict:

    """

    Retrieve one link request from Firestore.

    """



    normalized_request_id = (

        str(

            request_id or ""

        )

        .strip()

    )



    if not normalized_request_id:



        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail="Link request ID is required.",

        )

    db = firestore.client()

    snapshot = (

        db.collection(

            LINK_REQUESTS_COLLECTION

        )

        .document(

            normalized_request_id

        )

        .get()

    )





    if not snapshot.exists:



        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="Link request not found.",

        )





    data = (

        snapshot.to_dict()

        or {}

    )



    data["_documentId"] = snapshot.id



    return data





def get_user_name(

    user_id: str,

    fallback: str,

) -> str:

    """

    Retrieve a Finora user's display name.



    The supplied fallback is returned when the user document

    cannot be found or does not contain a usable name.

    """



    normalized_user_id = (

        str(

            user_id or ""

        )

        .strip()

    )



    if not normalized_user_id:

        return fallback





    db = firestore.client()



    snapshot = (

        db.collection(

            USERS_COLLECTION

        )

        .document(

            normalized_user_id

        )

        .get()

    )





    if not snapshot.exists:

        return fallback





    data = (

        snapshot.to_dict()

        or {}

    )





    return (

        str(

            data.get("name")

            or fallback

        )

        .strip()

        or fallback

    )





# ============================================================

# Link Notification Endpoint

# ============================================================



@router.post(

    "/notify",

    response_model=LinkNotificationResponse,

    status_code=status.HTTP_200_OK,

)

def notify_link_event(

    request: LinkNotificationRequest,

    current_user: AuthenticatedUser = Depends(

        get_current_user

    ),

) -> LinkNotificationResponse:

    """

    Send notification(s) for a verified Finora link event.



    Android supplies only:

        - requestId

        - eventType



    The backend retrieves the actual Provider and Student IDs

    from Firestore and verifies that the authenticated user is

    allowed to trigger the event.



    Notification behavior:



        LINK_REQUEST

            -> Student



        LINK_APPROVED

            -> Provider

            -> Student



        LINK_DECLINED

            -> Provider



        LINK_EXPIRED

            -> Provider

            -> Student



    Every created backend notification goes through the

    centralized notification service, which stores it in

    Firestore for the notification bell/history and attempts

    FCM push delivery.

    """



    # --------------------------------------------------------

    # Normalize / Validate Event

    # --------------------------------------------------------



    event_type = (

        normalize_event_type(

            request.eventType

        )

    )





    if (

        event_type

        not in SUPPORTED_LINK_EVENTS

    ):



        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail="Unsupported link notification event.",

        )





    # --------------------------------------------------------

    # Retrieve Verified Link Request

    # --------------------------------------------------------



    link_request = (

        get_link_request(

            request.requestId

        )

    )





    provider_id = (

        str(

            link_request.get(

                "providerId"

            )

            or ""

        )

        .strip()

    )





    student_id = (

        str(

            link_request.get(

                "studentId"

            )

            or ""

        )

        .strip()

    )





    request_status = (

        str(

            link_request.get(

                "status"

            )

            or ""

        )

        .strip()

        .lower()

    )





    if (

        not provider_id

        or not student_id

    ):



        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail=(

                "Link request contains invalid "

                "participant data."

            ),

        )





    # --------------------------------------------------------

    # Resolve Names

    # --------------------------------------------------------



    provider_name = (

        get_user_name(

            provider_id,

            "A provider",

        )

    )





    student_name = (

        get_user_name(

            student_id,

            "The student",

        )

    )





    # ========================================================

    # LINK REQUEST

    #

    # Provider initiated the request.

    #

    # Recipient:

    #     Student

    #

    # Student receives:

    #     - Firestore bell/history notification

    #     - FCM push

    # ========================================================



    if (

        event_type

        == EVENT_LINK_REQUEST

    ):



        if (

            current_user.uid

            != provider_id

        ):



            raise HTTPException(

                status_code=status.HTTP_403_FORBIDDEN,

                detail=(

                    "Only the requesting Provider may "

                    "trigger this notification."

                ),

            )





        if (

            request_status

            != "pending"

        ):



            raise HTTPException(

                status_code=status.HTTP_409_CONFLICT,

                detail=(

                    "The link request is no longer pending."

                ),

            )





        notification_id = (

            create_and_send_notification(

                user_id=

                    student_id,



                notification_type=

                    EVENT_LINK_REQUEST,



                title=

                    "New Link Request",



                message=(

                    f"{provider_name} sent you a "

                    "link request."

                ),



                student_id=

                    student_id,

            )

        )





    # ========================================================

    # LINK APPROVED

    #

    # Student approves the request.

    #

    # BOTH participants are notified.

    #

    # Provider:

    #     - Firestore bell/history

    #     - FCM push

    #

    # Student:

    #     - Firestore bell/history

    #     - FCM push

    # ========================================================



    elif (

        event_type

        == EVENT_LINK_APPROVED

    ):



        if (

            current_user.uid

            != student_id

        ):



            raise HTTPException(

                status_code=status.HTTP_403_FORBIDDEN,

                detail=(

                    "Only the requested Student may "

                    "trigger an approval notification."

                ),

            )





        if (

            request_status

            != "approved"

        ):



            raise HTTPException(

                status_code=status.HTTP_409_CONFLICT,

                detail=(

                    "The link request is not approved."

                ),

            )





        # ----------------------------------------------------

        # Notify Provider

        # ----------------------------------------------------



        provider_notification_id = (

            create_and_send_notification(

                user_id=

                    provider_id,



                notification_type=

                    EVENT_LINK_APPROVED,



                title=

                    "Link Request Approved",



                message=(

                    f"{student_name} approved your "

                    "link request."

                ),



                student_id=

                    student_id,

            )

        )





        # ----------------------------------------------------

        # Notify Student

        # ----------------------------------------------------



        student_notification_id = (

            create_and_send_notification(

                user_id=

                    student_id,



                notification_type=

                    EVENT_LINK_APPROVED,



                title=

                    "Account Linked",



                message=(

                    f"Your account is now linked with "

                    f"{provider_name}."

                ),



                student_id=

                    student_id,

            )

        )





        notification_id = (

            provider_notification_id

            or student_notification_id

        )





    # ========================================================

    # LINK DECLINED

    #

    # Student performs the decline action.

    #

    # Recipient:

    #     Provider

    #

    # Provider receives:

    #     - Firestore bell/history

    #     - FCM push

    # ========================================================



    elif (

        event_type

        == EVENT_LINK_DECLINED

    ):



        if (

            current_user.uid

            != student_id

        ):



            raise HTTPException(

                status_code=status.HTTP_403_FORBIDDEN,

                detail=(

                    "Only the requested Student may "

                    "trigger a decline notification."

                ),

            )





        if (

            request_status

            != "declined"

        ):



            raise HTTPException(

                status_code=status.HTTP_409_CONFLICT,

                detail=(

                    "The link request is not declined."

                ),

            )





        notification_id = (

            create_and_send_notification(

                user_id=

                    provider_id,



                notification_type=

                    EVENT_LINK_DECLINED,



                title=

                    "Link Request Declined",



                message=(

                    f"{student_name} declined your "

                    "link request."

                ),



                student_id=

                    student_id,

            )

        )





    # ========================================================

    # LINK EXPIRED

    #

    # Both participants are notified because the request is

    # no longer usable.

    #

    # Provider:

    #     - Firestore bell/history

    #     - FCM push

    #

    # Student:

    #     - Firestore bell/history

    #     - FCM push

    # ========================================================



    elif (

        event_type

        == EVENT_LINK_EXPIRED

    ):



        if (

            current_user.uid

            not in {

                provider_id,

                student_id,

            }

        ):



            raise HTTPException(

                status_code=status.HTTP_403_FORBIDDEN,

                detail=(

                    "You are not a participant in this "

                    "link request."

                ),

            )





        if (

            request_status

            != "expired"

        ):



            raise HTTPException(

                status_code=status.HTTP_409_CONFLICT,

                detail=(

                    "The link request is not expired."

                ),

            )





        # ----------------------------------------------------

        # Notify Provider

        # ----------------------------------------------------



        provider_notification_id = (

            create_and_send_notification(

                user_id=

                    provider_id,



                notification_type=

                    EVENT_LINK_EXPIRED,



                title=

                    "Link Request Expired",



                message=(

                    f"Your link request involving "

                    f"{student_name} has expired."

                ),



                student_id=

                    student_id,

            )

        )





        # ----------------------------------------------------

        # Notify Student

        # ----------------------------------------------------



        student_notification_id = (

            create_and_send_notification(

                user_id=

                    student_id,



                notification_type=

                    EVENT_LINK_EXPIRED,



                title=

                    "Link Request Expired",



                message=(

                    f"Your link request involving "

                    f"{provider_name} has expired."

                ),



                student_id=

                    student_id,

            )

        )

        notification_id = (

            provider_notification_id

            or student_notification_id

        )


    else:

        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail="Unsupported link notification event.",

        )



    # ========================================================

    # Duplicate Handling

    # ========================================================



    if (

        notification_id

        is None

    ):



        return LinkNotificationResponse(

            success=True,

            notificationId=None,

            skipped=True,

            message=(

                "A recent equivalent notification "

                "already exists."

            ),

        )





    return LinkNotificationResponse(

        success=True,

        notificationId=

            notification_id,

        skipped=False,

        message=(

            "Link notification created successfully."

        ),

    )





# ============================================================

# Secure Unlink Endpoint

# ============================================================



@router.post(

    "/unlink",

    response_model=UnlinkAccountsResponse,

    status_code=status.HTTP_200_OK,

)

def unlink_accounts(

    request: UnlinkAccountsRequest,

    current_user: AuthenticatedUser = Depends(

        get_current_user

    ),

) -> UnlinkAccountsResponse:

    """

    Securely remove an existing Provider-Student link.



    Either participant may unlink.



    The backend:



        1. verifies the requested participants

        2. verifies the authenticated participant

        3. verifies the actual Firestore link

        4. deletes the link

        5. notifies the Provider

        6. notifies the Student



    Both participant notifications are stored in Firestore

    for the notification bell/history and each independently

    attempts FCM push delivery.

    """



    # --------------------------------------------------------

    # Normalize Request

    # --------------------------------------------------------



    provider_id = (

        str(

            request.providerId

            or ""

        )

        .strip()

    )





    student_id = (

        str(

            request.studentId

            or ""

        )

        .strip()

    )





    if (

        not provider_id

        or not student_id

    ):



        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail=(

                "Provider ID and Student ID are required."

            ),

        )





    # --------------------------------------------------------

    # Verify Authenticated Participant

    # --------------------------------------------------------



    if (

        current_user.uid

        not in {

            provider_id,

            student_id,

        }

    ):



        raise HTTPException(

            status_code=status.HTTP_403_FORBIDDEN,

            detail=(

                "You are not allowed to unlink "

                "these accounts."

            ),

        )





    # --------------------------------------------------------

    # Resolve Link

    # --------------------------------------------------------



    link_id = (

        f"{provider_id}_{student_id}"

    )





    db = firestore.client()





    link_reference = (

        db.collection(

            LINKED_ACCOUNTS_COLLECTION

        )

        .document(

            link_id

        )

    )





    link_snapshot = (

        link_reference.get()

    )





    if not link_snapshot.exists:



        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail=(

                "The accounts are no longer linked."

            ),

        )





    link_data = (

        link_snapshot.to_dict()

        or {}

    )





    stored_provider_id = (

        str(

            link_data.get(

                "providerId"

            )

            or ""

        )

        .strip()

    )





    stored_student_id = (

        str(

            link_data.get(

                "studentId"

            )

            or ""

        )

        .strip()

    )





    # --------------------------------------------------------

    # Protect Against Forged Participant IDs

    # --------------------------------------------------------



    if (

        stored_provider_id

        != provider_id

        or stored_student_id

        != student_id

    ):



        raise HTTPException(

            status_code=status.HTTP_409_CONFLICT,

            detail=(

                "Linked-account data does not match."

            ),

        )





    # --------------------------------------------------------

    # Resolve Names Before Deleting Link

    # --------------------------------------------------------



    provider_name = (

        get_user_name(

            provider_id,

            "The provider",

        )

    )





    student_name = (

        get_user_name(

            student_id,

            "The student",

        )

    )





    # --------------------------------------------------------

    # Delete Link

    # --------------------------------------------------------



    try:



        link_reference.delete()



        logger.info(

            "Accounts unlinked successfully. "

            "provider=%s student=%s triggeredBy=%s",

            provider_id,

            student_id,

            current_user.uid,

        )





    except Exception as exc:



        logger.exception(

            "Failed to unlink provider=%s student=%s",

            provider_id,

            student_id,

        )



        raise HTTPException(

            status_code=

                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail="Failed to unlink accounts.",

        ) from exc





    # ========================================================

    # Notify Provider

    #

    # Firestore bell/history + FCM push

    # ========================================================



    try:



        create_and_send_notification(

            user_id=

                provider_id,



            notification_type=

                EVENT_ACCOUNT_UNLINKED,



            title=

                "Account Unlinked",



            message=(

                f"Your link with {student_name} "

                "has been removed."

            ),



            student_id=

                student_id,

        )





    except Exception:



        # The link has already been removed successfully.

        # Notification failure must not restore the link.



        logger.exception(

            "Provider unlink notification failed. "

            "provider=%s student=%s",

            provider_id,

            student_id,

        )





    # ========================================================

    # Notify Student

    #

    # Firestore bell/history + FCM push

    # ========================================================



    try:



        create_and_send_notification(

            user_id=

                student_id,



            notification_type=

                EVENT_ACCOUNT_UNLINKED,



            title=

                "Account Unlinked",



            message=(

                f"Your link with {provider_name} "

                "has been removed."

            ),



            student_id=

                student_id,

        )





    except Exception:



        logger.exception(

            "Student unlink notification failed. "

            "provider=%s student=%s",

            provider_id,

            student_id,

        )

    return UnlinkAccountsResponse(

        success=True,

        message="Accounts unlinked successfully.",

    )