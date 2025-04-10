from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from typing import Dict
from sqlalchemy.sql import func

from ..database import get_db
from ..models import Device

router = APIRouter(
    prefix="/stream",
    tags=["stream"],
    responses={
        200: {"description": "Stream key is valid"},
        404: {"description": "Stream key is invalid or device is inactive"},
        500: {"description": "Internal server error"}
    },
)

@router.get("/validate/{stream_key}")
async def validate_stream_key(stream_key: str, db: Session = Depends(get_db)):
    """
    Validate if a stream key exists and is associated with an active device.
    Returns:
        200: If stream key is valid and device is active
        404: If stream key is invalid or device is inactive
        500: If there's a server error
    """
    try:
        device = db.query(Device).filter(
            Device.stream_key == stream_key,
            Device.is_active == True
        ).first()
        
        if device is None:
            return Response(
                status_code=status.HTTP_404_NOT_FOUND,
                content="Invalid stream key or inactive device",
                media_type="text/plain",
                headers={
                    "X-Api-Status": "invalid_key",
                    "Content-Type": "text/plain"
                }
            )
        
        # Update last_seen_at timestamp
        device.last_seen_at = func.now()
        db.commit()
        
        return Response(
            status_code=status.HTTP_200_OK,
            content="Stream key validated",
            media_type="text/plain",
            headers={
                "X-Api-Status": "valid_key",
                "Content-Type": "text/plain"
            }
        )
    except Exception as e:
        return Response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content="Server error during validation",
            media_type="text/plain",
            headers={
                "X-Api-Status": "server_error",
                "Content-Type": "text/plain"
            }
        ) 