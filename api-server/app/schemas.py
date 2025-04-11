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
    recordings: list[Recording]
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
    user_id: int

    class Config:
        orm_mode = True

class DeviceList(BaseModel):
    devices: list[Device]
    count: int 