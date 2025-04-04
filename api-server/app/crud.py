from sqlalchemy.orm import Session
from . import models, schemas
from typing import List, Optional

def get_recording(db: Session, recording_id: int):
    return db.query(models.Recording).filter(models.Recording.id == recording_id).first()

def get_recordings(db: Session, skip: int = 0, limit: int = 100, stream_name: Optional[str] = None):
    query = db.query(models.Recording)
    
    if stream_name:
        query = query.filter(models.Recording.stream_name == stream_name)
    
    return query.order_by(models.Recording.created_at.desc()).offset(skip).limit(limit).all()

def create_recording(db: Session, recording: schemas.RecordingCreate):
    db_recording = models.Recording(**recording.dict())
    db.add(db_recording)
    db.commit()
    db.refresh(db_recording)
    return db_recording

def update_recording(db: Session, recording_id: int, recording: schemas.RecordingCreate):
    db_recording = db.query(models.Recording).filter(models.Recording.id == recording_id).first()
    
    if db_recording:
        for key, value in recording.dict().items():
            setattr(db_recording, key, value)
        
        db.commit()
        db.refresh(db_recording)
    
    return db_recording

def delete_recording(db: Session, recording_id: int):
    db_recording = db.query(models.Recording).filter(models.Recording.id == recording_id).first()
    
    if db_recording:
        db.delete(db_recording)
        db.commit()
        return True
    
    return False

def update_recording_metadata(db: Session, recording_id: int, metadata: dict):
    """Update the metadata of a recording"""
    db_recording = db.query(models.Recording).filter(models.Recording.id == recording_id).first()
    if db_recording is None:
        return None
    
    db_recording.recording_metadata = metadata
    db.commit()
    db.refresh(db_recording)
    return db_recording 