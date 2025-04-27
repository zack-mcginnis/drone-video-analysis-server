from sqlalchemy.orm import Session
from . import models, schemas
from typing import List, Optional

def get_recording(db: Session, recording_id: int, user_id: Optional[int] = None):
    """
    Get a recording by ID. If user_id is provided, checks if the user has access through their devices.
    
    Args:
        db: Database session
        recording_id: ID of the recording to retrieve
        user_id: Optional user ID to check permissions against
    
    Returns:
        Recording if found and user has access, None otherwise
    """
    # First get the recording
    recording = db.query(models.Recording).filter(
        models.Recording.id == recording_id
    ).first()
    
    if not recording:
        return None
        
    # If no user_id provided, just return the recording
    if user_id is None:
        return recording
        
    # Check if user has access through device association
    user_device = db.query(models.Device).filter(
        models.Device.users.any(id=user_id),
        models.Device.is_active == True,
        models.Device.stream_key == recording.stream_name
    ).first()
    
    # Return recording only if user has an associated device with matching stream key
    return recording if user_device else None

def get_recordings(db: Session, user_id: int, skip: int = 0, limit: int = 100, stream_name: Optional[str] = None):
    # Get all devices associated with the user
    user_devices = db.query(models.Device).join(models.Device.users).filter(models.User.id == user_id).all()
    
    # Get all stream keys from the user's devices
    stream_keys = [device.stream_key for device in user_devices]
    
    # Base query for recordings
    query = db.query(models.Recording)
    
    # Filter by stream keys if we have any devices
    if stream_keys:
        query = query.filter(models.Recording.stream_name.in_(stream_keys))
    
    # Additional stream name filter if provided
    if stream_name:
        query = query.filter(models.Recording.stream_name == stream_name)
    
    return query.order_by(models.Recording.created_at.desc()).offset(skip).limit(limit).all()

def create_recording(db: Session, recording: schemas.RecordingCreate):
    db_recording = models.Recording(**recording.dict())
    db.add(db_recording)
    db.commit()
    db.refresh(db_recording)
    return db_recording

def update_recording(db: Session, recording_id: int, recording: schemas.RecordingCreate, user_id: int):
    db_recording = db.query(models.Recording).filter(
        models.Recording.id == recording_id,
        models.Recording.user_id == user_id
    ).first()
    
    if db_recording:
        for key, value in recording.dict().items():
            setattr(db_recording, key, value)
        
        db.commit()
        db.refresh(db_recording)
    
    return db_recording

def delete_recording(db: Session, recording_id: int, user_id: int):
    db_recording = db.query(models.Recording).filter(
        models.Recording.id == recording_id,
        models.Recording.user_id == user_id
    ).first()
    
    if db_recording:
        db.delete(db_recording)
        db.commit()
        return True
    
    return False

def update_recording_metadata(db: Session, recording_id: int, metadata: dict, user_id: int):
    """Update the metadata of a recording"""
    db_recording = db.query(models.Recording).filter(
        models.Recording.id == recording_id,
        models.Recording.user_id == user_id
    ).first()
    
    if db_recording is None:
        raise ValueError(f"Recording not found for id={recording_id} and user_id={user_id}")
    
    db_recording.recording_metadata = metadata
    db.commit()
    db.refresh(db_recording)
    return db_recording 