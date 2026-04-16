# app/routes/uploads.py

import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.dependencies.auth import get_current_user
from app.supabase_client import supabase_db

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
BUCKET = "question-images"

SIGNATURES = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],
    "image/gif": [b"GIF87a", b"GIF89a"],
}


def _matches_magic_bytes(content_type: str, contents: bytes) -> bool:
    signatures = SIGNATURES.get(content_type, [])
    if not signatures:
        return False

    if content_type == "image/webp":
        return contents.startswith(b"RIFF") and len(contents) >= 12 and contents[8:12] == b"WEBP"

    return any(contents.startswith(sig) for sig in signatures)


@router.post("/question-image")
async def upload_question_image(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    # --- Validate MIME type ---
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. "
                   f"Allowed: jpeg, png, webp, gif"
        )

    # --- Read and validate size ---
    contents = await file.read()
    if len(contents) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File too large. Maximum size is 5MB."
        )

    if not _matches_magic_bytes(file.content_type, contents):
        raise HTTPException(
            status_code=415,
            detail="File content does not match the declared image type."
        )

    # --- Generate unique storage path ---
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    filename = f"{user.id}/{uuid.uuid4()}.{ext}"

    # --- Upload to Supabase Storage ---
    try:
        supabase_db.storage.from_(BUCKET).upload(
            path=filename,
            file=contents,
            file_options={"content-type": file.content_type},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # --- Build public URL ---
    url_response = supabase_db.storage.from_(BUCKET).get_public_url(filename)
    image_url = url_response.get("publicURL") if isinstance(url_response, dict) else str(url_response)

    return {
        "image_url": image_url,
        "filename": filename,   # store this if you want to delete later
    }