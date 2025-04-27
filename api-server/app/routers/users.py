from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import logging
from .. import database, models
from ..services.auth import auth_service
from ..utils.stream_keys import generate_stream_key, validate_stream_key

# Configure logging
logger = logging.getLogger(__name__)

class DeviceResponse(BaseModel):
    id: int
    name: str
    stream_key: str
    created_at: datetime
    last_seen_at: Optional[datetime]
    is_active: bool

    class Config:
        orm_mode = True

class UserResponse(BaseModel):
    id: int
    email: str
    auth0_id: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    devices: List[DeviceResponse]

    class Config:
        orm_mode = True

class Auth0UserInfo(BaseModel):
    email: str
    auth0_id: str

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={404: {"description": "Not found"}},
)

@router.post("/stream-keys", response_model=List[str])
async def create_stream_key(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_admin_user)
):
    """Create a new stream key for the current user. Admin only."""
    # Generate a new stream key
    stream_key = generate_stream_key()
    
    # Get current stream keys
    stream_keys = current_user.stream_keys or []
    
    # Add the new key
    stream_keys.append(stream_key)
    
    # Update user
    current_user.stream_keys = stream_keys
    db.commit()
    
    return stream_keys

@router.get("/stream-keys", response_model=List[str])
async def get_stream_keys(
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Get all stream keys for the current user."""
    return current_user.stream_keys or []

@router.delete("/stream-keys/{stream_key}", response_model=List[str])
async def delete_stream_key(
    stream_key: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_admin_user)
):
    """Delete a stream key for the current user. Admin only."""
    if not validate_stream_key(stream_key):
        raise HTTPException(status_code=400, detail="Invalid stream key format")
    
    # Get current stream keys
    stream_keys = current_user.stream_keys or []
    
    # Remove the key if it exists
    if stream_key in stream_keys:
        stream_keys.remove(stream_key)
        current_user.stream_keys = stream_keys
        db.commit()
    
    return stream_keys

@router.post("/post-login", response_model=UserResponse)
async def post_login(
    user_info: Auth0UserInfo,
    db: Session = Depends(database.get_db)
):
    """
    Endpoint to be called after successful Auth0 login.
    Creates a new user if they don't exist, or returns existing user data.
    Also ensures the user has at least one device.
    """
    logger.info(f"Post-login called with auth0_id: {user_info.auth0_id}, email: {user_info.email}")
    
    # Check if user exists by auth0_id
    user = db.query(models.User).filter(models.User.auth0_id == user_info.auth0_id).first()
    
    if user:
        logger.info(f"Found existing user with id: {user.id}")
        return user
    
    # If not found by auth0_id, check by email as fallback
    user = db.query(models.User).filter(models.User.email == user_info.email).first()
    if user:
        # User found by email but not auth0_id - this should be rare
        # This might happen if auth0_id was changed or migrated
        logger.info(f"Found user by email with id: {user.id}, updating auth0_id")
        user.auth0_id = user_info.auth0_id
        db.commit()
        db.refresh(user)
        return user
        
    # User not found - implement retry logic for creation
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Check one more time in case user was created in another request
            user = db.query(models.User).filter(models.User.auth0_id == user_info.auth0_id).first()
            if user:
                logger.info(f"User was created by another process, found with id: {user.id}")
                return user
                
            logger.info("User not found, creating new user")
            # Create new user
            user = models.User(
                email=user_info.email,
                auth0_id=user_info.auth0_id,
                is_active=True
            )
            
            db.add(user)
            logger.info("Added new user to session")
            
            db.flush()  # Flush to get the user ID
            logger.info(f"Flushed session, got user id: {user.id}")
            
            # Create a default device for the user
            stream_key = generate_stream_key()
            logger.info(f"Generated stream key: {stream_key} for default device")
            
            default_device = models.Device(
                name="My First Device",
                stream_key=stream_key,
                is_active=True,
                user_id=user.id
            )
            db.add(default_device)
            logger.info("Added default device to session")
            
            db.commit()
            logger.info("Committed transaction successfully")
            db.refresh(user)
            logger.info(f"Refreshed user object, has {len(user.devices)} devices")
            
            return user
            
        except Exception as e:
            retry_count += 1
            db.rollback()
            logger.warning(f"Attempt {retry_count} failed to create user: {str(e)}")
            
            if retry_count >= max_retries:
                logger.error(f"Database error while creating user: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create user: {str(e)}"
                )
                
            # Small delay to prevent immediate retry
            import asyncio
            await asyncio.sleep(0.2)
            
            # After waiting, check if another process created the user
            user = db.query(models.User).filter(models.User.auth0_id == user_info.auth0_id).first()
            if user:
                logger.info(f"User was created by another process during retry, found with id: {user.id}")
                return user 