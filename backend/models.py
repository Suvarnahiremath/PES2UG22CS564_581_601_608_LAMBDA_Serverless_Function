from pydantic import BaseModel, Field
from typing import Optional, List
import datetime

class FunctionBase(BaseModel):
    name: str
    route: str
    language: str
    code: str
    timeout: Optional[int] = 30
    memory: Optional[int] = 128

class FunctionCreate(FunctionBase):
    pass

class FunctionUpdate(BaseModel):
    name: Optional[str] = None
    route: Optional[str] = None
    language: Optional[str] = None
    code: Optional[str] = None
    timeout: Optional[int] = None
    memory: Optional[int] = None

class Function(FunctionBase):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    
    class Config:
        orm_mode = True

class ExecutionBase(BaseModel):
    function_id: int
    status: str
    virtualization: str
    duration: Optional[float] = None
    error_message: Optional[str] = None
    memory_used: Optional[float] = None
    cpu_used: Optional[float] = None

class ExecutionCreate(ExecutionBase):
    pass

class Execution(ExecutionBase):
    id: int
    start_time: datetime.datetime
    end_time: Optional[datetime.datetime] = None
    
    class Config:
        orm_mode = True

class FunctionInvoke(BaseModel):
    parameters: dict = Field(default_factory=dict)

class FunctionInvokeResponse(BaseModel):
    result: dict
    execution_id: int
    duration: float