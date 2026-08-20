from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.cloudinary_service import (
    CloudinaryConfigurationError,
    CloudinaryUploadError,
    upload_profile_image,
)


router = APIRouter(
    prefix="/profile",
    tags=["Profile"],
)


@router.post("/upload")
async def upload_profile_picture(
    user_id: str = Form(...),
    image: UploadFile = File(...),
):
    try:
        if not image.content_type:
            raise HTTPException(
                status_code=400,
                detail="Image content type is missing.",
            )

        if not image.content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail="Uploaded file must be an image.",
            )

        image_bytes = await image.read()

        if not image_bytes:
            raise HTTPException(
                status_code=400,
                detail="Uploaded image is empty.",
            )

        image_url = upload_profile_image(
            image_bytes=image_bytes,
            user_id=user_id,
        )

        return {
            "success": True,
            "profileImageUrl": image_url,
        }

    except HTTPException:
        raise

    except CloudinaryConfigurationError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    except CloudinaryUploadError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Profile upload failed: {exc}",
        )