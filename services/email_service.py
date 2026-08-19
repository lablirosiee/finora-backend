import os
import requests


class EmailConfigurationError(Exception):
    pass


class EmailAuthenticationError(Exception):
    pass


class EmailDeliveryError(Exception):
    pass


BREVO_API_KEY = os.getenv(
    "BREVO_API_KEY",
    "",
).strip()

FINORA_FROM_EMAIL = os.getenv(
    "FINORA_FROM_EMAIL",
    "",
).strip()


def build_otp_html(otp: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="en">
<body style="
    margin: 0;
    padding: 30px 15px;
    background-color: #f4f7fb;
    font-family: Arial, Helvetica, sans-serif;
">
    <div style="
        max-width: 520px;
        margin: 0 auto;
        background-color: #ffffff;
        border-radius: 14px;
        padding: 32px;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.08);
    ">

        <h1 style="
            margin: 0 0 8px 0;
            color: #2563eb;
            font-size: 28px;
        ">
            Finora
        </h1>

        <h2 style="
            margin: 0 0 18px 0;
            color: #1f2937;
            font-size: 22px;
        ">
            Verify your email address
        </h2>

        <p style="
            color: #4b5563;
            line-height: 1.6;
        ">
            Use the verification code below to continue
            creating your Finora account.
        </p>

        <div style="
            margin: 24px 0;
            padding: 20px;
            border-radius: 10px;
            background-color: #eff6ff;
            color: #2563eb;
            font-size: 34px;
            font-weight: bold;
            letter-spacing: 8px;
            text-align: center;
        ">
            {otp}
        </div>

        <p style="
            color: #6b7280;
            line-height: 1.6;
        ">
            Please do not share this code with anyone.
        </p>

        <p style="
            margin-top: 24px;
            color: #9ca3af;
            font-size: 13px;
            line-height: 1.5;
        ">
            If you did not request this code,
            you may safely ignore this email.
        </p>

    </div>
</body>
</html>
""".strip()


def build_otp_text(otp: str) -> str:
    return f"""
Hello!

Your Finora verification code is:

{otp}

This code is intended only for your Finora account verification.

Please do not share this code with anyone.

If you did not request this code, you may safely ignore this email.

– Finora
""".strip()


def send_otp_email(
    recipient_email: str,
    otp: str,
) -> None:

    if not BREVO_API_KEY:
        raise EmailConfigurationError(
            "BREVO_API_KEY is not configured."
        )

    if not FINORA_FROM_EMAIL:
        raise EmailConfigurationError(
            "FINORA_FROM_EMAIL is not configured."
        )

    recipient_email = recipient_email.strip()
    otp = otp.strip()

    if not recipient_email:
        raise EmailDeliveryError(
            "Recipient email is required."
        )

    if len(otp) != 6 or not otp.isdigit():
        raise EmailDeliveryError(
            "OTP must contain exactly 6 digits."
        )

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    payload = {
        "sender": {
            "name": "Finora",
            "email": FINORA_FROM_EMAIL,
        },
        "to": [
            {
                "email": recipient_email,
            }
        ],
        "subject": "Your Finora Verification Code",
        "htmlContent": build_otp_html(otp),
        "textContent": build_otp_text(otp),
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30,
        )

        if response.status_code in (200, 201, 202):
            return

        if response.status_code in (401, 403):
            raise EmailAuthenticationError(
                f"Brevo authentication failed: {response.text}"
            )

        raise EmailDeliveryError(
            f"Brevo returned HTTP {response.status_code}: "
            f"{response.text}"
        )

    except EmailAuthenticationError:
        raise

    except EmailDeliveryError:
        raise

    except requests.RequestException as exc:
        raise EmailDeliveryError(
            f"Failed to connect to Brevo: {exc}"
        ) from exc