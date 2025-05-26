from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, JSON, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

# Association table for User-Device many-to-many relationship
user_device_association = Table(
    "user_device_association",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("device_id", Integer, ForeignKey("devices.id"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

class Recording(Base):
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True, index=True)
    stream_name = Column(String(255), nullable=False, index=True)
    local_mp4_path = Column(String(1024), nullable=True)
    s3_mp4_path = Column(String(1024), nullable=True)
    local_hls_path = Column(String(1024), nullable=True)
    s3_hls_path = Column(String(1024), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    file_size = Column(BigInteger, nullable=True)
    duration = Column(Integer, nullable=True)
    environment = Column(String(50), nullable=False)
    recording_metadata = Column(JSON, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relationship with User model
    owner = relationship("User", back_populates="recordings")

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    stream_key = Column(String(8), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Updated relationship with User model to be many-to-many
    users = relationship("User", secondary=user_device_association, back_populates="devices")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    auth0_id = Column(String(255), unique=True, index=True)
    
    # Relationships
    recordings = relationship("Recording", back_populates="owner")
    devices = relationship("Device", secondary=user_device_association, back_populates="users") 