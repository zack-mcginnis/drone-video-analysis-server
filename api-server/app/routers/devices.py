from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
import secrets
import string

from ..database import get_db
from ..models import Device, User
from ..schemas import DeviceCreate, Device as DeviceSchema, DeviceList, DeviceUpdate
from ..services.auth import auth_service

router = APIRouter(
    prefix="/devices",
    tags=["devices"]
)

def generate_stream_key(length: int = 8) -> str:
    """Generate a random stream key."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@router.post("/", response_model=DeviceSchema)
async def create_device(
    device: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_admin_user)
):
    """Create a new device. Admin only."""
    db_device = Device(
        name=device.name,
        stream_key=generate_stream_key(),
        user_id=current_user.id
    )
    
    try:
        db.add(db_device)
        db.commit()
        db.refresh(db_device)
        return db_device
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error creating device. Please try again."
        )

@router.get("/", response_model=DeviceList)
async def get_devices(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    """Get all devices for the authenticated user."""
    devices = db.query(Device).filter(
        Device.user_id == current_user.id
    ).offset(skip).limit(limit).all()
    
    total_count = db.query(Device).filter(
        Device.user_id == current_user.id
    ).count()
    
    return DeviceList(devices=devices, count=total_count)

@router.get("/{device_id}", response_model=DeviceSchema)
async def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    """Get a specific device by ID."""
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.user_id == current_user.id
    ).first()
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    return device

@router.put("/{device_id}", response_model=DeviceSchema)
async def update_device(
    device_id: int,
    device_update: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    """Update a device."""
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.user_id == current_user.id
    ).first()
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    for field, value in device_update.dict(exclude_unset=True).items():
        setattr(device, field, value)
    
    try:
        db.commit()
        db.refresh(device)
        return device
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error updating device. Please try again."
        )

@router.delete("/{device_id}")
async def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_admin_user)
):
    """Delete a device. Admin only."""
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.user_id == current_user.id
    ).first()
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    db.delete(device)
    db.commit()
    return {"message": "Device deleted successfully"} 