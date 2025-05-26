from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

class RecordingBase(BaseModel):
    stream_name: str
    local_mp4_path: Optional[str] = None
    s3_mp4_path: Optional[str] = None
    local_hls_path: Optional[str] = None
    s3_hls_path: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[int] = None
    environment: str
    recording_metadata: Optional[Dict[str, Any]] = None
    user_id: int

class RecordingCreate(RecordingBase):
    pass

class Recording(RecordingBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class RecordingList(BaseModel):
    recordings: List[Recording]
    count: int

class DeviceBase(BaseModel):
    name: str

class DeviceCreate(DeviceBase):
    pass

class DeviceUpdate(BaseModel):
    name: str
    is_active: Optional[bool] = None

class Device(DeviceBase):
    id: int
    stream_key: str
    created_at: datetime
    updated_at: datetime
    last_seen_at: Optional[datetime]
    is_active: bool
    user_id: int  # For backward compatibility with existing clients

    class Config:
        orm_mode = True
        # Enable arbitrary_types_allowed to support SQLAlchemy objects and dict conversion
        arbitrary_types_allowed = True

class DeviceList(BaseModel):
    devices: List[Device]
    count: int 