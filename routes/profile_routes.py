import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from firebase_admin import firestore

from dependencies.auth import (
    AuthenticatedUser,
    get_current_user,
)
from services.cloudinary_service import (
    CloudinaryConfigurationError,
    CloudinaryDeleteError,
    CloudinaryUploadError,
    delete_profile_image,
    upload_profile_image,
)


router = APIRouter(
    prefix="/profile",
    tags=["Profile"],
)

logger = logging.getLogger(__name__)

db = firestore.client()


# ============================================================
# Constants
# ============================================================

MAX_PROFILE_IMAGE_SIZE_BYTES = (
    5 * 1024 * 1024
)

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


# ============================================================
# Upload Profile Picture
# ============================================================

@router.post("/upload")
async def upload_profile_picture(
    image: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
):
    """
    Upload a profile picture for the authenticated user.

    The Firebase UID comes from the verified Firebase ID token.
    The client never supplies the user ID directly.
    """

    try:

        # ----------------------------------------------------
        # Validate content type
        # ----------------------------------------------------

        content_type = (
            image.content_type
            or ""
        ).lower().strip()

        if not content_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image content type is missing.",
            )

        if (
            content_type
            not in ALLOWED_IMAGE_CONTENT_TYPES
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Profile picture must be "
                    "JPEG, PNG, or WebP."
                ),
            )

        # ----------------------------------------------------
        # Read image
        # ----------------------------------------------------

        image_bytes = await image.read()

        if not image_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded image is empty.",
            )

        # ----------------------------------------------------
        # Validate size
        # ----------------------------------------------------

        if (
            len(image_bytes)
            > MAX_PROFILE_IMAGE_SIZE_BYTES
        ):
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    "Profile image must not exceed 5 MB."
                ),
            )

        # ----------------------------------------------------
        # Upload to Cloudinary
        # ----------------------------------------------------

        image_url = upload_profile_image(
            image_bytes=image_bytes,
            user_id=current_user.uid,
        )

        if not image_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Profile image upload did not "
                    "return an image URL."
                ),
            )

        # ----------------------------------------------------
        # Persist URL in Firestore
        # ----------------------------------------------------

        db.collection("users") \
            .document(current_user.uid) \
            .update(
                {
                    "profileImageUrl": image_url,
                }
            )

        return {
            "success": True,
            "profileImageUrl": image_url,
        }

    except HTTPException:
        raise

    except CloudinaryConfigurationError as exc:

        logger.exception(
            "Cloudinary configuration error "
            "during profile upload."
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Profile image service is "
                "not configured correctly."
            ),
        ) from exc

    except CloudinaryUploadError as exc:

        logger.exception(
            "Cloudinary profile upload failed "
            "for user %s.",
            current_user.uid,
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Unable to upload profile image."
            ),
        ) from exc

    except Exception as exc:

        logger.exception(
            "Unexpected profile upload failure "
            "for user %s.",
            current_user.uid,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Profile image upload failed."
            ),
        ) from exc

    finally:

        await image.close()


# ============================================================
# Delete Profile Picture
# ============================================================

@router.delete("/image")
async def delete_profile_picture(
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
):
    """
    Delete the authenticated user's profile picture.

    The Firebase UID comes from the verified Firebase ID token.
    """

    try:

        # ----------------------------------------------------
        # Delete from Cloudinary
        # ----------------------------------------------------

        delete_profile_image(
            user_id=current_user.uid
        )

        # ----------------------------------------------------
        # Clear Firestore URL
        # ----------------------------------------------------

        db.collection("users") \
            .document(current_user.uid) \
            .update(
                {
                    "profileImageUrl": None,
                }
            )

        return {
            "success": True,
            "message": "Profile picture removed.",
        }

    except CloudinaryConfigurationError as exc:

        logger.exception(
            "Cloudinary configuration error "
            "during profile deletion."
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Profile image service is "
                "not configured correctly."
            ),
        ) from exc

    except CloudinaryDeleteError as exc:

        logger.exception(
            "Cloudinary profile deletion failed "
            "for user %s.",
            current_user.uid,
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Unable to delete profile image."
            ),
        ) from exc

    except Exception as exc:

        logger.exception(
            "Unexpected profile deletion failure "
            "for user %s.",
            current_user.uid,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Profile image deletion failed."
            ),
        ) from exc