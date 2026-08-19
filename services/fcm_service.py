import os

import firebase_admin
from firebase_admin import credentials, firestore, messaging


SERVICE_ACCOUNT_PATH = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_PATH",
    "/etc/secrets/firebase-service-account.json"
)


def initialize_firebase():
    if firebase_admin._apps:
        return

    if not os.path.exists(SERVICE_ACCOUNT_PATH):
        raise RuntimeError(
            "Firebase service account file is missing."
        )

    cred = credentials.Certificate(
        SERVICE_ACCOUNT_PATH
    )

    firebase_admin.initialize_app(cred)


initialize_firebase()


def send_push_to_user(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    notification_id: str = "",
    student_id: str = "",
) -> str:

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
        user_data.get("fcmToken", "")
    ).strip()

    if not fcm_token:
        raise ValueError(
            "Target user has no FCM token."
        )

    data = {
        "type": notification_type,
        "title": title,
        "body": message,
        "message": message,
        "notificationId": notification_id,
        "studentId": student_id,
    }

    push_message = messaging.Message(
        data=data,
        token=fcm_token,
    )

    response = messaging.send(
        push_message
    )

    return response