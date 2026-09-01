import os

import cloudinary
import cloudinary.uploader


# ============================================================
# Exceptions
# ============================================================


class CloudinaryConfigurationError(Exception):
    pass


class CloudinaryUploadError(Exception):
    pass


class CloudinaryDeleteError(Exception):
    pass


# ============================================================
# Constants
# ============================================================


PROFILE_IMAGE_FOLDER = "finora/profile_images"


# ============================================================
# Cloudinary Initialization
# ============================================================


def initialize_cloudinary() -> None:

    cloudinary_url = os.getenv(
        "CLOUDINARY_URL",
        "",
    ).strip()

    if not cloudinary_url:
        raise CloudinaryConfigurationError(
            "CLOUDINARY_URL is not configured."
        )

    cloudinary.config(
        secure=True
    )


initialize_cloudinary()


# ============================================================
# Helpers
# ============================================================


def get_profile_image_public_id(
    user_id: str,
) -> str:

    normalized_user_id = user_id.strip()

    if not normalized_user_id:
        raise ValueError(
            "User ID is required."
        )

    return (
        f"{PROFILE_IMAGE_FOLDER}/"
        f"{normalized_user_id}"
    )


# ============================================================
# Upload Profile Image
# ============================================================


def upload_profile_image(
    image_bytes: bytes,
    user_id: str,
) -> str:

    if not image_bytes:
        raise CloudinaryUploadError(
            "Image data is required."
        )

    normalized_user_id = user_id.strip()

    if not normalized_user_id:
        raise CloudinaryUploadError(
            "User ID is required."
        )

    try:

        result = cloudinary.uploader.upload(
            image_bytes,
            folder=PROFILE_IMAGE_FOLDER,
            public_id=normalized_user_id,
            overwrite=True,
            invalidate=True,
            resource_type="image",
        )

        secure_url = str(
            result.get(
                "secure_url",
                "",
            )
        ).strip()

        if not secure_url:
            raise CloudinaryUploadError(
                "Cloudinary did not return an image URL."
            )

        return secure_url

    except CloudinaryUploadError:
        raise

    except Exception as exc:
        raise CloudinaryUploadError(
            "Failed to upload profile image."
        ) from exc


# ============================================================
# Delete Profile Image
# ============================================================


def delete_profile_image(
    user_id: str,
) -> bool:

    normalized_user_id = user_id.strip()

    if not normalized_user_id:
        raise CloudinaryDeleteError(
            "User ID is required."
        )

    public_id = get_profile_image_public_id(
        normalized_user_id
    )

    try:

        result = cloudinary.uploader.destroy(
            public_id,
            resource_type="image",
            invalidate=True,
        )

        delete_result = str(
            result.get(
                "result",
                "",
            )
        ).strip().lower()

        if delete_result == "ok":
            return True
            
       # Cloudinary may return "not found" if:
        # - the user never had a profile image,
        # - it was already deleted,
        # - Firestore was previously cleared.
        #
        # For a DELETE-style operation, treating this
        # as success makes the operation idempotent.

         

        if delete_result == "not found":
            return True

        raise CloudinaryDeleteError(
            "Cloudinary could not delete the profile image."
        )

    except CloudinaryDeleteError:
        raise

    except Exception as exc:
        raise CloudinaryDeleteError(
            "Failed to delete profile image."
        ) from exc