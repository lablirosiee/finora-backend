import smtplib
from email.message import EmailMessage

from config import (
    GMAIL_APP_PASSWORD,
    GMAIL_USER,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_TIMEOUT_SECONDS,
)


class EmailConfigurationError(Exception):
    pass


class EmailAuthenticationError(Exception):
    pass


class EmailDeliveryError(Exception):
    pass


def build_otp_email(
    recipient_email: str,
    otp: str,
) -> EmailMessage:
    message = EmailMessage()

    message["Subject"] = (
        "Your Finora Verification Code"
    )

    message["From"] = (
        f"Finora <{GMAIL_USER}>"
    )

    message["To"] = recipient_email

    message.set_content(
        f"""
Hello!

Your Finora verification code is:

{otp}

This code is intended only for your Finora account verification.
Please do not share it with anyone.

If you did not request this code, you may ignore this email.

– Finora
""".strip()
    )

    message.add_alternative(
        f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <title>Finora Verification Code</title>
</head>

<body style="
    margin: 0;
    padding: 30px 15px;
    background-color: #f4f7fb;
    font-family: Arial, Helvetica, sans-serif;
">
    <div style="
        max-width: 520px;
        margin: 0 auto;
        padding: 32px;
        background-color: #ffffff;
        border-radius: 14px;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.08);
    ">
        <h1 style="
            margin: 0 0 8px 0;
            color: #2563eb;
            font-size: 30px;
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
            Use the verification code below to
            continue creating your Finora account.
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
            Please do not share this code with
            anyone.
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
""".strip(),
        subtype="html",
    )

    return message


def send_otp_email(
    recipient_email: str,
    otp: str,
) -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise EmailConfigurationError(
            "Email credentials are not configured."
        )

    message = build_otp_email(
        recipient_email=recipient_email,
        otp=otp,
    )

    try:
        with smtplib.SMTP_SSL(
            host=SMTP_HOST,
            port=SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as smtp:
            smtp.login(
                GMAIL_USER,
                GMAIL_APP_PASSWORD,
            )

            smtp.send_message(message)

    except smtplib.SMTPAuthenticationError as exc:
        raise EmailAuthenticationError(
            "Gmail authentication failed. "
            "Check the Gmail address and App Password."
        ) from exc

    except Exception as exc:
        raise EmailDeliveryError(
            f"Failed to send OTP email: {exc}"
        ) from exc