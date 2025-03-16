from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class RecordingBase(BaseModel):
    stream_name: str
    file_path: str
    s3_path: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[int] = None
    environment: str
    recording_metadata: Optional[Dict[str, Any]] = None

class RecordingCreate(RecordingBase):
    pass

class Recording(RecordingBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class RecordingList(BaseModel):
    recordings: list[Recording]
    count: int 