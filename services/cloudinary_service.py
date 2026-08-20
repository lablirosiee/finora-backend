import os

import cloudinary
import cloudinary.uploader


class CloudinaryConfigurationError(Exception):
    pass


class CloudinaryUploadError(Exception):
    pass


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


def upload_profile_image(
    image_bytes: bytes,
    user_id: str,
) -> str:

    if not image_bytes:
        raise CloudinaryUploadError(
            "Image data is required."
        )

    if not user_id.strip():
        raise CloudinaryUploadError(
            "User ID is required."
        )

    try:
        result = cloudinary.uploader.upload(
            image_bytes,
            folder="finora/profile_images",
            public_id=user_id.strip(),
            overwrite=True,
            invalidate=True,
            resource_type="image",
        )

        secure_url = str(
            result.get("secure_url", "")
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
            f"Failed to upload profile image: {exc}"
        ) from exc