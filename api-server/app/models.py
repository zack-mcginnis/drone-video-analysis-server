from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, JSON
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