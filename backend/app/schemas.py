from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class FileInfo(BaseModel):
    filename: str
    size: int
    last_modified: datetime

class ExecutionResult(BaseModel):
    filename: str
    status: str
    output: str
    error: str
    return_code: int
    execution_time: float
    memory_usage: float

class HistoryItem(BaseModel):
    id: int
    filename: str
    status: str
    output: str
    error: str
    return_code: int
    execution_time: float
    memory_usage: float
    created_at: datetime