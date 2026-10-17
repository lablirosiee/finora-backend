# migrate_email_verification.py

import firebase_admin
from firebase_admin import auth, firestore


# ============================================================
# FIREBASE INITIALIZATION
# ============================================================

try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app()


db = firestore.client()


# ============================================================
# LEGACY OTP USERS
# ============================================================
#
# Add ONLY UIDs of old Finora accounts that you personally know
# completed the old Finora OTP verification process.
#
# Do NOT place every user here automatically.
#
# Example:
#
# LEGACY_OTP_UIDS = {
#     "abc123",
#     "xyz789",
# }
#
# If none, leave this empty first and run the script to see
# which users need manual review.
# ============================================================

LEGACY_OTP_UIDS = {
    "UvsTCgLeTQMDEdzAWdN8cQSDDYE2",
}

# ============================================================
# MIGRATION
# ============================================================

def migrate_email_verification():

    users_reference = db.collection("users")

    migrated = 0
    already_migrated = 0
    needs_review = 0
    errors = 0

    print("\n========================================")
    print("FINORA EMAIL VERIFICATION MIGRATION")
    print("========================================\n")

    for document in users_reference.stream():

        uid = document.id
        data = document.to_dict() or {}

        email = str(
            data.get("email", "")
        ).strip()

        existing_verified = data.get(
            "emailVerified"
        )

        verification_method = str(
            data.get(
                "verificationMethod",
                ""
            )
        ).strip()

        email_verified_at = data.get(
            "emailVerifiedAt"
        )

        # ----------------------------------------------------
        # Already has a verified status
        # ----------------------------------------------------

        if existing_verified is True:

            already_migrated += 1

            print(
                f"[SKIP] {email or uid} "
                f"already verified."
            )

            continue

        try:

            firebase_user = auth.get_user(uid)

        except Exception as exception:

            errors += 1

            print(
                f"[ERROR] {email or uid}: "
                f"unable to read Firebase Auth user - "
                f"{exception}"
            )

            continue

        # ----------------------------------------------------
        # METHOD 1:
        # Firebase already confirms the email was verified.
        #
        # Useful for accounts created under Finora's older
        # Firebase email-verification-link implementation.
        # ----------------------------------------------------

        if firebase_user.email_verified:

            users_reference \
                .document(uid) \
                .update(
                    {
                        "emailVerified": True,
                        "verificationMethod":
                            "FIREBASE_LEGACY",
                        "emailVerifiedAt":
                            firestore.SERVER_TIMESTAMP,
                    }
                )

            migrated += 1

            print(
                f"[MIGRATED] {email or uid} "
                f"using Firebase legacy verification."
            )

            continue

        # ----------------------------------------------------
        # METHOD 2:
        # Firestore already contains OTP verification evidence.
        # ----------------------------------------------------

        if (
            verification_method.upper() == "OTP"
            or email_verified_at is not None
        ):

            users_reference \
                .document(uid) \
                .update(
                    {
                        "emailVerified": True,
                        "verificationMethod":
                            verification_method
                            if verification_method
                            else "OTP_LEGACY",
                    }
                )

            migrated += 1

            print(
                f"[MIGRATED] {email or uid} "
                f"using existing Finora verification metadata."
            )

            continue

        # ----------------------------------------------------
        # METHOD 3:
        # Manually confirmed old OTP account.
        #
        # Only accounts explicitly placed in LEGACY_OTP_UIDS
        # are migrated through this branch.
        # ----------------------------------------------------

        if uid in LEGACY_OTP_UIDS:

            users_reference \
                .document(uid) \
                .update(
                    {
                        "emailVerified": True,
                        "verificationMethod":
                            "OTP_LEGACY",
                        "emailVerifiedAt":
                            firestore.SERVER_TIMESTAMP,
                    }
                )

            migrated += 1

            print(
                f"[MIGRATED] {email or uid} "
                f"as confirmed legacy OTP account."
            )

            continue

        # ----------------------------------------------------
        # No proof available.
        #
        # Do NOT silently mark the account verified.
        # ----------------------------------------------------

        needs_review += 1

        print(
            f"[REVIEW] {email or uid} | "
            f"UID={uid} | "
            f"No verification metadata found."
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    print("\n========================================")
    print("MIGRATION COMPLETE")
    print("========================================")

    print(f"Migrated:        {migrated}")
    print(f"Already verified:{already_migrated}")
    print(f"Needs review:    {needs_review}")
    print(f"Errors:          {errors}")

    print("========================================\n")


if __name__ == "__main__":
    migrate_email_verification()