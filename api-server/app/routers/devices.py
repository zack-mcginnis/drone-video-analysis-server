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
        is_active=True
    )
    
    try:
        # Add device to db
        db.add(db_device)
        db.flush()
        
        # Add relationship to current user
        db_device.users.append(current_user)
        
        db.commit()
        db.refresh(db_device)
        
        # Construct response
        response = dict(db_device.__dict__)
        response["user_id"] = current_user.id  # For schema compatibility
        
        return response
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
        Device.users.contains(current_user)
    ).offset(skip).limit(limit).all()
    
    total_count = db.query(Device).filter(
        Device.users.contains(current_user)
    ).count()
    
    # Add user_id for schema compatibility
    device_list = []
    for device in devices:
        device_dict = dict(device.__dict__)
        device_dict["user_id"] = current_user.id
        device_list.append(device_dict)
    
    return DeviceList(devices=device_list, count=total_count)

@router.get("/{device_id}", response_model=DeviceSchema)
async def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    """Get a specific device by ID."""
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.users.contains(current_user)
    ).first()
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    # Add user_id for schema compatibility
    response = dict(device.__dict__)
    response["user_id"] = current_user.id
    
    return response

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
        Device.users.contains(current_user)
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
        
        # Add user_id for schema compatibility
        response = dict(device.__dict__)
        response["user_id"] = current_user.id
        
        return response
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
        Device.users.contains(current_user)
    ).first()
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    # Remove device from all related users
    device.users = []
    
    # Delete the device
    db.delete(device)
    db.commit()
    
    return {"message": "Device deleted successfully"} 