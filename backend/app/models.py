from sqlalchemy import Column, Integer, String, DateTime, Float, Text, ForeignKey
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ExecutionHistory(Base):
    __tablename__ = "execution_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String, nullable=False)
    status = Column(String, nullable=False)  # Finished, Error, Stopped, Timeout, Running
    output = Column(Text, default="")
    error = Column(Text, default="")
    return_code = Column(Integer, default=0)
    execution_time = Column(Float, default=0.0)
    memory_usage = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())