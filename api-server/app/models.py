from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Recording(Base):
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True, index=True)
    stream_name = Column(String(255), nullable=False, index=True)
    file_path = Column(String(1024), nullable=False)
    s3_path = Column(String(1024), nullable=True)
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relationship with User model
    owner = relationship("User", back_populates="devices")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    auth0_id = Column(String(255), unique=True, index=True)
    
    # Relationships
    recordings = relationship("Recording", back_populates="owner")
    devices = relationship("Device", back_populates="owner") 