import logging



from datetime import datetime, timezone







from fastapi import (



    APIRouter,



    Depends,



    HTTPException,



    status,



)



from firebase_admin import firestore



from google.cloud.firestore_v1 import transactional







from schemas.notification_schemas import (



    NotificationEventRequest,



    NotificationEventResponse,



)



from services.auth_service import (



    AuthenticatedUser,



    get_current_user,



)



from services.notification_service import (



    create_and_send_notification,



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



ALLOWANCES_COLLECTION = "allowances"



EXPENSES_COLLECTION = "expenses"







# Backend-only state for category-budget crossing protection.



BUDGET_ALERT_STATES_COLLECTION = "budget_alert_states"



# Backend-only idempotency state for allowance-cycle-ended alerts.

ALLOWANCE_CYCLE_ALERT_STATES_COLLECTION = "allowance_cycle_alert_states"











# ============================================================



# Own-Finance Events



# ============================================================







EVENT_ALLOWANCE_LOW = "ALLOWANCE_LOW"



EVENT_UNUSUAL_SPENDING = "UNUSUAL_SPENDING"



EVENT_FINANCIAL_RISK = "FINANCIAL_RISK"



EVENT_BUDGET_EXCEEDED = "BUDGET_EXCEEDED"



EVENT_FORECAST_UPDATE = "FORECAST_UPDATE"



EVENT_SMART_ADVICE = "SMART_ADVICE"



EVENT_ALLOWANCE_CYCLE_ENDED = "ALLOWANCE_CYCLE_ENDED"







SUPPORTED_OWN_FINANCE_EVENTS = {



    EVENT_ALLOWANCE_LOW,



    EVENT_UNUSUAL_SPENDING,



    EVENT_FINANCIAL_RISK,



    EVENT_BUDGET_EXCEEDED,



    EVENT_FORECAST_UPDATE,



    EVENT_SMART_ADVICE,



    EVENT_ALLOWANCE_CYCLE_ENDED,

}











# ============================================================



# Events Forwarded from Student to Linked Provider



#



# BUDGET_EXCEEDED is intentionally NOT included here.



# Category-budget alerts use their own category/cycle-aware



# fan-out so the Provider does not receive duplicates.



# ============================================================







PROVIDER_FORWARDABLE_EVENTS = {



    EVENT_ALLOWANCE_LOW,



    EVENT_UNUSUAL_SPENDING,



    EVENT_FINANCIAL_RISK,



    EVENT_FORECAST_UPDATE,



    EVENT_ALLOWANCE_CYCLE_ENDED,

}











# ============================================================



# Linked-Student Provider Events



# ============================================================







EVENT_STUDENT_ALLOWANCE_LOW = "STUDENT_ALLOWANCE_LOW"



EVENT_STUDENT_UNUSUAL_SPENDING = "STUDENT_UNUSUAL_SPENDING"



EVENT_STUDENT_FINANCIAL_RISK = "STUDENT_FINANCIAL_RISK"



EVENT_STUDENT_BUDGET_EXCEEDED = "STUDENT_BUDGET_EXCEEDED"



EVENT_STUDENT_FORECAST_UPDATE = "STUDENT_FORECAST_UPDATE"



EVENT_STUDENT_ALLOWANCE_CYCLE_ENDED = "STUDENT_ALLOWANCE_CYCLE_ENDED"











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







    return str(event_type or "").strip().upper()











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







    normalized_user_id = str(user_id or "").strip()







    if not normalized_user_id:



        return fallback







    try:



        db = firestore.client()







        snapshot = (



            db.collection(USERS_COLLECTION)



            .document(normalized_user_id)



            .get()



        )







        if not snapshot.exists:



            return fallback







        data = snapshot.to_dict() or {}







        name = str(data.get("name") or "").strip()







        return name if name else fallback







    except Exception:



        logger.exception(



            "Unable to retrieve user name. uid=%s",



            normalized_user_id,



        )



        return fallback











# ============================================================



# User Role



# ============================================================







def get_user_role(



    user_id: str,



) -> str:



    """



    Retrieve a Finora user's role from Firestore.







    Expected values:



        - student



        - provider







    The value is normalized to lowercase.



    """







    normalized_user_id = str(user_id or "").strip()







    if not normalized_user_id:



        return ""







    try:



        db = firestore.client()







        snapshot = (



            db.collection(USERS_COLLECTION)



            .document(normalized_user_id)



            .get()



        )







        if not snapshot.exists:



            logger.warning(



                "User document does not exist while resolving role. uid=%s",



                normalized_user_id,



            )



            return ""







        data = snapshot.to_dict() or {}







        return str(data.get("role") or "").strip().lower()







    except Exception:



        logger.exception(



            "Unable to retrieve user role. uid=%s",



            normalized_user_id,



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



    the linked_accounts collection. When a link is removed,



    its active linked-account document is removed.



    """







    normalized_student_id = str(student_id or "").strip()







    if not normalized_student_id:



        return []







    db = firestore.client()







    try:



        snapshots = (



            db.collection(LINKED_ACCOUNTS_COLLECTION)



            .where(



                "studentId",



                "==",



                normalized_student_id,



            )



            .stream()



        )







        provider_ids: list[str] = []







        for snapshot in snapshots:



            data = snapshot.to_dict() or {}







            provider_id = str(



                data.get("providerId") or ""



            ).strip()







            if (



                provider_id



                and provider_id not in provider_ids



            ):



                provider_ids.append(provider_id)







        return provider_ids







    except Exception:



        logger.exception(



            "Failed to retrieve linked Providers for student=%s.",



            normalized_student_id,



        )



        return []











# ============================================================



# Allowance Cycle Ended Idempotency



# ============================================================







def _allowance_cycle_alert_state_id(



    user_id: str,



    cycle_end: int,



) -> str:



    return f"{user_id}_{cycle_end}"











def _claim_allowance_cycle_end_notification(



    *,



    user_id: str,



    cycle_end: int,



) -> bool:



    """Atomically claim one user allowance cycle exactly once."""







    db = firestore.client()







    state_reference = (



        db.collection(



            ALLOWANCE_CYCLE_ALERT_STATES_COLLECTION



        )



        .document(



            _allowance_cycle_alert_state_id(



                user_id=user_id,



                cycle_end=cycle_end,



            )



        )



    )







    transaction = db.transaction()







    @transactional



    def claim(



        transaction,



    ) -> bool:







        snapshot = state_reference.get(



            transaction=transaction



        )







        if snapshot.exists:



            return False







        transaction.set(



            state_reference,



            {



                "userId": user_id,



                "cycleEndDate": cycle_end,



                "createdAt": firestore.SERVER_TIMESTAMP,



            },



        )







        return True







    return claim(



        transaction



    )











def _release_allowance_cycle_end_notification_claim(



    *,



    user_id: str,



    cycle_end: int,



) -> None:







    db = firestore.client()







    (



        db.collection(



            ALLOWANCE_CYCLE_ALERT_STATES_COLLECTION



        )



        .document(



            _allowance_cycle_alert_state_id(



                user_id=user_id,



                cycle_end=cycle_end,



            )



        )



        .delete()



    )











# ============================================================



# Category Budget Helpers



# ============================================================







def _safe_float(



    value,



    default: float = 0.0,



) -> float:



    """



    Convert a Firestore numeric value safely to float.



    """







    try:



        return float(value)



    except (TypeError, ValueError):



        return default











def _normalize_budget_category(



    value,



) -> str:



    """



    Convert Finora category labels to canonical keys.



    """







    normalized = (



        str(value or "")



        .strip()



        .lower()



        .replace("-", "")



        .replace("_", "")



        .replace(" ", "")



    )







    if normalized == "essential":



        return "essential"







    if normalized == "nonessential":



        return "non_essential"







    return ""











def _format_peso(



    value: float,



) -> str:



    """



    Format a monetary value for notification text.



    """







    return f"₱{max(value, 0.0):,.2f}"











def _budget_state_document_id(



    user_id: str,



    cycle_start: int,



    category_key: str,



) -> str:



    """



    One deterministic state document per:



        user + allowance cycle + category



    """







    return (



        f"{user_id}_"



        f"{cycle_start}_"



        f"{category_key}"



    )











# ============================================================



# Atomic Category Budget State Transition



# ============================================================







def _update_budget_alert_state(



    *,



    user_id: str,



    cycle_start: int,



    cycle_end: int,



    category_key: str,



    category_name: str,



    budget: float,



    spent: float,



    is_exceeded: bool,



) -> bool:



    """



    Atomically update one category's alert state.







    Returns True only when the category transitions from:



        NOT EXCEEDED -> EXCEEDED







    This provides:



        - one alert per exceeded episode



        - independent Essential/Non-Essential state



        - automatic reset after edit/delete drops spending below budget



        - automatic fresh state for a new allowance cycle



    """







    db = firestore.client()







    state_reference = (



        db.collection(BUDGET_ALERT_STATES_COLLECTION)



        .document(



            _budget_state_document_id(



                user_id=user_id,



                cycle_start=cycle_start,



                category_key=category_key,



            )



        )



    )







    transaction = db.transaction()







    @transactional



    def apply_state(



        transaction,



    ) -> bool:



        snapshot = state_reference.get(



            transaction=transaction



        )







        previous_data = (



            snapshot.to_dict()



            if snapshot.exists



            else {}



        ) or {}







        was_exceeded = bool(



            previous_data.get(



                "isExceeded",



                False,



            )



        )







        transaction.set(



            state_reference,



            {



                "userId": user_id,



                "cycleStartDate": cycle_start,



                "cycleEndDate": cycle_end,



                "category": category_name,



                "categoryKey": category_key,



                "budget": budget,



                "spent": spent,



                "isExceeded": is_exceeded,



                "updatedAt": firestore.SERVER_TIMESTAMP,



            },



            merge=True,



        )







        return (



            is_exceeded



            and not was_exceeded



        )







    return apply_state(



        transaction



    )











# ============================================================



# Category Budget Notification Evaluation



# ============================================================







def process_category_budget_notifications(



    user_id: str,



) -> tuple[list[str], int]:



    """



    Evaluate the authenticated user's current Essential and



    Non-Essential category budgets.







    Student:



        - own Firestore bell



        - own FCM push



        - approved/current linked Provider bell + push







    Provider:



        - own Firestore bell



        - own FCM push



        - never forwarded to a Student







    Duplicate protection:



        - separate per category



        - separate per allowance cycle



        - reset when spending drops below the category budget



    """







    normalized_user_id = str(user_id or "").strip()







    if not normalized_user_id:



        raise ValueError(



            "User ID is required."



        )







    db = firestore.client()







    # --------------------------------------------------------



    # Current Allowance



    # --------------------------------------------------------







    allowance_snapshot = (



        db.collection(ALLOWANCES_COLLECTION)



        .document(normalized_user_id)



        .get()



    )







    if not allowance_snapshot.exists:



        logger.info(



            "Category budget evaluation skipped because no "



            "allowance exists. uid=%s",



            normalized_user_id,



        )



        return [], 0







    allowance_data = (



        allowance_snapshot.to_dict()



        or {}



    )







    cycle_start = int(



        allowance_data.get(



            "cycleStartDate"



        ) or 0



    )







    cycle_end = int(



        allowance_data.get(



            "cycleEndDate"



        ) or 0



    )







    if (



        cycle_start <= 0



        or cycle_end <= cycle_start



    ):



        logger.warning(



            "Category budget evaluation skipped because the "



            "allowance cycle is invalid. uid=%s start=%s end=%s",



            normalized_user_id,



            cycle_start,



            cycle_end,



        )



        return [], 0







    now_ms = int(



        datetime.now(



            timezone.utc



        ).timestamp()



        * 1000



    )







    if (



        now_ms < cycle_start



        or now_ms > cycle_end



    ):



        logger.info(



            "Category budget evaluation skipped because the "



            "allowance cycle is not active. uid=%s",



            normalized_user_id,



        )



        return [], 0







    essential_budget = max(



        _safe_float(



            allowance_data.get(



                "essentialBudget"



            )



        ),



        0.0,



    )







    non_essential_budget = max(



        _safe_float(



            allowance_data.get(



                "nonEssentialBudget"



            )



        ),



        0.0,



    )







    # --------------------------------------------------------



    # Current-Cycle Expenses



    # --------------------------------------------------------







    cycle_start_datetime = datetime.fromtimestamp(



        cycle_start / 1000.0,



        tz=timezone.utc,



    )







    cycle_end_datetime = datetime.fromtimestamp(



        cycle_end / 1000.0,



        tz=timezone.utc,



    )







    expense_documents = (



        db.collection(EXPENSES_COLLECTION)



        .where(



            "userId",



            "==",



            normalized_user_id,



        )



        .where(



            "expenseDate",



            ">=",



            cycle_start_datetime,



        )



        .where(



            "expenseDate",



            "<=",



            cycle_end_datetime,



        )



        .stream()



    )







    essential_spent = 0.0



    non_essential_spent = 0.0







    for expense_snapshot in expense_documents:



        expense_data = (



            expense_snapshot.to_dict()



            or {}



        )







        amount = max(



            _safe_float(



                expense_data.get(



                    "amount"



                )



            ),



            0.0,



        )







        category_key = (



            _normalize_budget_category(



                expense_data.get(



                    "category"



                )



            )



        )







        if category_key == "essential":



            essential_spent += amount







        elif category_key == "non_essential":



            non_essential_spent += amount







    # --------------------------------------------------------



    # Role + Linked Providers



    # --------------------------------------------------------







    user_role = get_user_role(



        normalized_user_id



    )







    is_student = (



        user_role == "student"



    )







    provider_ids = (



        get_linked_provider_ids(



            normalized_user_id



        )



        if is_student



        else []



    )







    owner_name = get_user_name(



        normalized_user_id,



        "The student",



    )







    # --------------------------------------------------------



    # Evaluate Essential and Non-Essential independently



    # --------------------------------------------------------







    categories = (



        (



            "essential",



            "Essential",



            essential_budget,



            essential_spent,



        ),



        (



            "non_essential",



            "Non-Essential",



            non_essential_budget,



            non_essential_spent,



        ),



    )







    owner_notification_ids: list[str] = []



    provider_notifications_created = 0







    for (



        category_key,



        category_name,



        budget,



        spent,



    ) in categories:







        # Finora considers 100% utilization as the budget limit



        # having been reached. Anything above it is exceeded.



        threshold_reached = (



            budget > 0.0



            and spent >= budget



        )







        should_notify = (



            _update_budget_alert_state(



                user_id=normalized_user_id,



                cycle_start=cycle_start,



                cycle_end=cycle_end,



                category_key=category_key,



                category_name=category_name,



                budget=budget,



                spent=spent,



                is_exceeded=threshold_reached,



            )



        )







        if not should_notify:



            continue







        exceeded_by = max(



            spent - budget,



            0.0,



        )







        is_strictly_exceeded = (



            exceeded_by > 0.0



        )







        own_title = (



            f"{category_name} Budget Exceeded"



            if is_strictly_exceeded



            else f"{category_name} Budget Limit Reached"



        )







        own_message = (



            (



                "You have exceeded your "



                f"{_format_peso(budget)} "



                f"{category_name} budget by "



                f"{_format_peso(exceeded_by)}."



            )



            if is_strictly_exceeded



            else (



                f"You have reached your "



                f"{_format_peso(budget)} "



                f"{category_name} budget limit."



            )



        )







        # ----------------------------------------------------



        # Owner Bell + Push



        # ----------------------------------------------------







        try:



            owner_notification_id = (



                create_and_send_notification(



                    user_id=normalized_user_id,



                    notification_type=EVENT_BUDGET_EXCEEDED,



                    title=own_title,



                    message=own_message,



                )



            )







            owner_notification_ids.append(



                owner_notification_id



            )







        except Exception:



            # Firestore notification creation failed.



            # Reset the crossing state so a later evaluation



            # can retry instead of permanently suppressing it.



            try:



                _update_budget_alert_state(



                    user_id=normalized_user_id,



                    cycle_start=cycle_start,



                    cycle_end=cycle_end,



                    category_key=category_key,



                    category_name=category_name,



                    budget=budget,



                    spent=spent,



                    is_exceeded=False,



                )



            except Exception:



                logger.exception(



                    "Failed to reset category budget state "



                    "after notification failure. "



                    "uid=%s category=%s",



                    normalized_user_id,



                    category_key,



                )







            raise







        # ----------------------------------------------------



        # Student -> Linked Provider(s)



        # ----------------------------------------------------







        if is_student:



            provider_title = (



                "Student Budget Alert"



            )







            provider_message = (



                (



                    f"{owner_name} has exceeded the allocated "



                    f"{category_name} budget for the current "



                    "allowance cycle."



                )



                if is_strictly_exceeded



                else (



                    f"{owner_name} has reached the allocated "



                    f"{category_name} budget limit for the "



                    "current allowance cycle."



                )



            )







            for provider_id in provider_ids:



                try:



                    create_and_send_notification(



                        user_id=provider_id,



                        notification_type=(



                            EVENT_STUDENT_BUDGET_EXCEEDED



                        ),



                        title=provider_title,



                        message=provider_message,



                        student_id=normalized_user_id,



                    )







                    provider_notifications_created += 1







                except Exception:



                    # One Provider failure must not prevent the



                    # owner's notification or other Providers.



                    logger.exception(



                        "Failed to create linked-Provider "



                        "category budget notification. "



                        "provider=%s student=%s category=%s",



                        provider_id,



                        normalized_user_id,



                        category_key,



                    )







    logger.info(



        "Category budget evaluation completed. "



        "uid=%s ownerAlerts=%d providerAlerts=%d "



        "essentialBudget=%.2f essentialSpent=%.2f "



        "nonEssentialBudget=%.2f nonEssentialSpent=%.2f",



        normalized_user_id,



        len(owner_notification_ids),



        provider_notifications_created,



        essential_budget,



        essential_spent,



        non_essential_budget,



        non_essential_spent,



    )







    return (



        owner_notification_ids,



        provider_notifications_created,



    )











# ============================================================



# Provider Fan-Out



#



# Used for non-category financial monitoring events.



# ============================================================







def notify_linked_providers(



    student_id: str,



    own_event_type: str,



) -> int:



    """



    Send the appropriate financial monitoring notification



    to every Provider currently linked to the Student.







    Smart Advice is intentionally not forwarded.







    Category-budget alerts are also intentionally excluded



    because they use category/cycle-aware processing above.



    """







    provider_ids = get_linked_provider_ids(



        student_id



    )







    if not provider_ids:



        logger.info(



            "No linked Providers found for student=%s.",



            student_id,



        )



        return 0







    student_name = get_user_name(



        student_id,



        "The student",



    )







    if own_event_type == EVENT_ALLOWANCE_LOW:



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







    elif own_event_type == EVENT_UNUSUAL_SPENDING:



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







    elif own_event_type == EVENT_FINANCIAL_RISK:



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







    elif own_event_type == EVENT_FORECAST_UPDATE:



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







    created_count = 0







    for provider_id in provider_ids:



        try:



            notification_id = (



                create_notification_if_not_recent(



                    user_id=provider_id,



                    notification_type=provider_event_type,



                    title=title,



                    message=message,



                    student_id=student_id,



                    within_hours=within_hours,



                )



            )







            if notification_id is not None:



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



            # prevent the owner's notification or notifications



            # to other linked Providers.



            logger.exception(



                "Failed to create linked-Provider "



                "notification. provider=%s student=%s type=%s",



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



    - Linked Provider recipients are resolved by the backend.



    - Provider own-finance activity is never sent to Students.



    - Smart Advice remains private to the account owner.



    """







    event_type = normalize_event_type(



        request.eventType



    )







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



            status_code=(



                status.HTTP_400_BAD_REQUEST



            ),



            detail=(



                "Unsupported own-finance "



                "notification event."



            ),



        )







    # ========================================================



    # ALLOWANCE CYCLE ENDED



    # ========================================================
    # ALLOWANCE CYCLE ENDED
    #
    # Own-cycle notification applies to BOTH supported Finora
    # financial roles.
    #
    # Student:
    #   - Student receives own bell + push.
    #   - Linked Provider(s) also receive Student Allowance
    #     Cycle Ended bell + push.
    #
    # Provider:
    #   - Provider receives own bell + push.
    #   - Provider personal-finance activity is NEVER forwarded
    #     to linked Students.
    # ========================================================

    if event_type == EVENT_ALLOWANCE_CYCLE_ENDED:

        db = firestore.client()

        user_role = get_user_role(
            current_user.uid
        )

        if user_role not in {
            "student",
            "provider",
        }:
            return NotificationEventResponse(
                success=True,
                notificationId=None,
                skipped=True,
                message=(
                    "Allowance-cycle-ended notification "
                    "is not supported for this account role."
                ),
            )

        allowance_snapshot = (
            db.collection(
                ALLOWANCES_COLLECTION
            )
            .document(
                current_user.uid
            )
            .get()
        )

        if not allowance_snapshot.exists:
            return NotificationEventResponse(
                success=True,
                notificationId=None,
                skipped=True,
                message="No allowance cycle was found.",
            )

        allowance_data = (
            allowance_snapshot.to_dict()
            or {}
        )

        try:
            cycle_end = int(
                allowance_data.get(
                    "cycleEndDate"
                )
                or 0
            )
        except (TypeError, ValueError):
            cycle_end = 0

        if cycle_end <= 0:
            return NotificationEventResponse(
                success=True,
                notificationId=None,
                skipped=True,
                message="Allowance cycle end date is invalid.",
            )

        now_ms = int(
            datetime.now(
                timezone.utc
            ).timestamp()
            * 1000
        )

        if now_ms <= cycle_end:
            return NotificationEventResponse(
                success=True,
                notificationId=None,
                skipped=True,
                message="Allowance cycle is still active.",
            )

        should_notify = (
            _claim_allowance_cycle_end_notification(
                user_id=current_user.uid,
                cycle_end=cycle_end,
            )
        )

        if not should_notify:
            return NotificationEventResponse(
                success=True,
                notificationId=None,
                skipped=True,
                message=(
                    "Allowance-cycle-ended notification "
                    "was already created for this cycle."
                ),
            )

        owner_message = (
            (
                "Your allowance cycle has ended. "
                "Set a new allowance to continue "
                "budget tracking, or wait for your "
                "linked Provider to assign the next one."
            )
            if user_role == "student"
            else
            (
                "Your allowance cycle has ended. "
                "Set a new allowance to continue "
                "budget tracking."
            )
        )

        try:
            notification_id = (
                create_and_send_notification(
                    user_id=current_user.uid,
                    notification_type=EVENT_ALLOWANCE_CYCLE_ENDED,
                    title="Allowance Cycle Ended",
                    message=owner_message,
                )
            )

        except Exception as exception:
            try:
                _release_allowance_cycle_end_notification_claim(
                    user_id=current_user.uid,
                    cycle_end=cycle_end,
                )
            except Exception:
                logger.exception(
                    "Failed to release allowance-cycle-ended "
                    "notification claim. user=%s cycleEnd=%s",
                    current_user.uid,
                    cycle_end,
                )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Failed to create allowance-cycle-ended "
                    "notification."
                ),
            ) from exception

        provider_notifications_created = 0

        if user_role == "student":
            student_name = get_user_name(
                current_user.uid,
                "The student",
            )

            for provider_id in get_linked_provider_ids(
                current_user.uid
            ):
                try:
                    create_and_send_notification(
                        user_id=provider_id,
                        notification_type=(
                            EVENT_STUDENT_ALLOWANCE_CYCLE_ENDED
                        ),
                        title="Student Allowance Cycle Ended",
                        message=(
                            f"{student_name}'s allowance cycle "
                            "has ended. You may assign a new "
                            "allowance for the next cycle."
                        ),
                        student_id=current_user.uid,
                    )

                    provider_notifications_created += 1

                except Exception:
                    logger.exception(
                        "Failed to create Provider "
                        "allowance-cycle-ended notification. "
                        "provider=%s student=%s",
                        provider_id,
                        current_user.uid,
                    )

        return NotificationEventResponse(
            success=True,
            notificationId=notification_id,
            skipped=False,
            message=(
                "Allowance-cycle-ended notification created. "
                + (
                    f"Linked Providers notified: "
                    f"{provider_notifications_created}."
                    if user_role == "student"
                    else
                    "Provider own-cycle notification created."
                )
            ),
        )


    # ========================================================



    # CATEGORY BUDGET EVALUATION



    #



    # This event is handled separately because it needs:



    # - Essential vs Non-Essential evaluation



    # - allowance-cycle-aware duplicate protection



    # - threshold reset after edit/delete



    # - category-specific Provider fan-out



    # ========================================================







    if event_type == EVENT_BUDGET_EXCEEDED:



        try:



            (



                owner_notification_ids,



                provider_notifications_created,



            ) = process_category_budget_notifications(



                current_user.uid



            )







        except Exception as exception:



            logger.exception(



                "Category budget notification evaluation "



                "failed. uid=%s",



                current_user.uid,



            )







            raise HTTPException(



                status_code=(



                    status.HTTP_500_INTERNAL_SERVER_ERROR



                ),



                detail=(



                    "Failed to evaluate category "



                    "budget notifications."



                ),



            ) from exception







        if not owner_notification_ids:



            return NotificationEventResponse(



                success=True,



                notificationId=None,



                skipped=True,



                message=(



                    "No new category budget alert "



                    "was required."



                ),



            )







        return NotificationEventResponse(



            success=True,



            notificationId=(



                owner_notification_ids[0]



            ),



            skipped=False,



            message=(



                f"Created "



                f"{len(owner_notification_ids)} "



                "category budget alert(s) and "



                f"{provider_notifications_created} "



                "linked Provider alert(s)."



            ),



        )







    # ========================================================



    # OTHER OWN-FINANCE EVENTS



    # ========================================================







    if event_type == EVENT_ALLOWANCE_LOW:



        notification_id = (



            create_notification_if_not_recent(



                user_id=current_user.uid,



                notification_type=EVENT_ALLOWANCE_LOW,



                title="Low Allowance",



                message=(



                    "Your remaining allowance is "



                    "running low."



                ),



                within_hours=24,



            )



        )







    elif event_type == EVENT_UNUSUAL_SPENDING:



        notification_id = (



            create_notification_if_not_recent(



                user_id=current_user.uid,



                notification_type=EVENT_UNUSUAL_SPENDING,



                title="Unusual Spending Detected",



                message=(



                    "Your recent spending is higher "



                    "than usual."



                ),



                within_hours=24,



            )



        )







    elif event_type == EVENT_FINANCIAL_RISK:



        notification_id = (



            create_notification_if_not_recent(



                user_id=current_user.uid,



                notification_type=EVENT_FINANCIAL_RISK,



                title="Financial Risk Alert",



                message=(



                    "Your current spending pattern may "



                    "put your allowance at risk."



                ),



                within_hours=24,



            )



        )







    elif event_type == EVENT_FORECAST_UPDATE:



        notification_id = (



            create_notification_if_not_recent(



                user_id=current_user.uid,



                notification_type=EVENT_FORECAST_UPDATE,



                title="Forecast Updated",



                message=(



                    "Your allowance forecast has been "



                    "updated."



                ),



                within_hours=12,



            )



        )







    elif event_type == EVENT_SMART_ADVICE:



        notification_id = (



            create_notification_if_not_recent(



                user_id=current_user.uid,



                notification_type=EVENT_SMART_ADVICE,



                title="Smart Spending Advice",



                message=(



                    "A new spending insight is available. "



                    "Check Finora for advice on managing "



                    "your allowance."



                ),



                within_hours=12,



            )



        )







    else:



        # Defensive fallback. BUDGET_EXCEEDED has already



        # returned above.



        raise HTTPException(



            status_code=(



                status.HTTP_400_BAD_REQUEST



            ),



            detail=(



                "Unsupported notification event."



            ),



        )







    # ========================================================



    # LINKED PROVIDER FAN-OUT



    # ========================================================







    provider_notifications_created = 0







    try:



        user_role = get_user_role(



            current_user.uid



        )







        logger.info(



            "Notification owner role resolved. "



            "uid=%s role=%s",



            current_user.uid,



            user_role or "UNKNOWN",



        )







        if (



            user_role == "student"



            and event_type



            in PROVIDER_FORWARDABLE_EVENTS



        ):



            provider_notifications_created = (



                notify_linked_providers(



                    student_id=current_user.uid,



                    own_event_type=event_type,



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







        elif (



            user_role == "student"



            and event_type == EVENT_SMART_ADVICE



        ):



            logger.info(



                "Student Smart Advice remains private "



                "to the Student. uid=%s",



                current_user.uid,



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



        # authenticated user's own notification request to fail.



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
