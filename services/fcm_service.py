import os

import firebase_admin
from firebase_admin import credentials, firestore, messaging


# ============================================================
# Firebase Configuration
# ============================================================

SERVICE_ACCOUNT_PATH = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_PATH",
    "/etc/secrets/firebase-service-account.json",
).strip()


# ============================================================
# Firebase Initialization
# ============================================================

def initialize_firebase() -> None:
    """
    Initialize Firebase Admin SDK once.

    On Render, the service account file should normally be:
    /etc/secrets/firebase-service-account.json
    """

    # Firebase is already initialized
    try:
        firebase_admin.get_app()
        return
    except ValueError:
        pass

    if not SERVICE_ACCOUNT_PATH:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_PATH is not configured."
        )

    if not os.path.isfile(SERVICE_ACCOUNT_PATH):
        raise RuntimeError(
            f"Firebase service account file is missing at: "
            f"{SERVICE_ACCOUNT_PATH}"
        )

    try:
        credential = credentials.Certificate(
            SERVICE_ACCOUNT_PATH
        )

        firebase_admin.initialize_app(
            credential
        )

    except Exception as exc:
        raise RuntimeError(
            f"Failed to initialize Firebase Admin SDK: {exc}"
        ) from exc


# Initialize Firebase when this module loads.
initialize_firebase()


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

    user_id = user_id.strip()
    notification_type = notification_type.strip()
    title = title.strip()
    message = message.strip()
    notification_id = notification_id.strip()
    student_id = student_id.strip()

    if not user_id:
        raise ValueError(
            "Target user ID is required."
        )

    if not notification_type:
        raise ValueError(
            "Notification type is required."
        )

    if not title:
        raise ValueError(
            "Notification title is required."
        )

    if not message:
        raise ValueError(
            "Notification message is required."
        )

    # --------------------------------------------------------
    # Get user's FCM token
    # --------------------------------------------------------

    db = firestore.client()

    user_document = (
        db.collection("users")
        .document(user_id)
        .get()
    )

    if not user_document.exists:
        raise ValueError(
            "Target user does not exist."
        )

    user_data = user_document.to_dict() or {}

    fcm_token = str(
        user_data.get("fcmToken") or ""
    ).strip()

    if not fcm_token:
        raise ValueError(
            "Target user has no FCM token."
        )

    # --------------------------------------------------------
    # Build FCM data payload
    # --------------------------------------------------------

    data = {
        "type": notification_type,
        "title": title,
        "body": message,
        "message": message,
        "notificationId": notification_id,
        "studentId": student_id,
    }

    # --------------------------------------------------------
    # Send FCM message
    # --------------------------------------------------------

    push_message = messaging.Message(
        token=fcm_token,
        data=data,
    )

    try:
        response = messaging.send(
            push_message
        )

        return response

    except messaging.UnregisteredError as exc:
        raise ValueError(
            "The user's FCM token is no longer valid. "
            "The app must register a new token."
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            f"Failed to send FCM notification: {exc}"
        ) from exc