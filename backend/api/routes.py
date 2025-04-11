from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import datetime

from backend.database.db import get_db, Function as DBFunction, Execution as DBExecution
from backend.models import Function, FunctionCreate, FunctionUpdate, Execution, FunctionInvoke, FunctionInvokeResponse
from backend.execution.executor_factory import ExecutorFactory
from backend.metrics.collector import metrics_collector

router = APIRouter()
executor_factory = ExecutorFactory()

# Function CRUD endpoints
@router.post("/functions/", response_model=Function)
def create_function(function: FunctionCreate, db: Session = Depends(get_db)):
    db_function = DBFunction(
        name=function.name,
        route=function.route,
        language=function.language,
        code=function.code,
        timeout=function.timeout,
        memory=function.memory
    )
    
    # Check if function with same name or route already exists
    existing_function = db.query(DBFunction).filter(
        (DBFunction.name == function.name) | (DBFunction.route == function.route)
    ).first()
    
    if existing_function:
        raise HTTPException(status_code=400, detail="Function with this name or route already exists")
    
    db.add(db_function)
    db.commit()
    db.refresh(db_function)
    
    # Prepare the function in both virtualization technologies
    docker_executor = executor_factory.get_executor("docker")
    gvisor_executor = executor_factory.get_executor("gvisor")
    
    docker_executor.prepare_function(db_function)
    gvisor_executor.prepare_function(db_function)
    
    return db_function

@router.get("/functions/", response_model=List[Function])
def read_functions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    functions = db.query(DBFunction).offset(skip).limit(limit).all()
    return functions

@router.get("/functions/{function_id}", response_model=Function)
def read_function(function_id: int, db: Session = Depends(get_db)):
    db_function = db.query(DBFunction).filter(DBFunction.id == function_id).first()
    if db_function is None:
        raise HTTPException(status_code=404, detail="Function not found")
    return db_function

@router.put("/functions/{function_id}", response_model=Function)
def update_function(function_id: int, function: FunctionUpdate, db: Session = Depends(get_db)):
    db_function = db.query(DBFunction).filter(DBFunction.id == function_id).first()
    if db_function is None:
        raise HTTPException(status_code=404, detail="Function not found")
    
    # Update fields if provided
    if function.name is not None:
        db_function.name = function.name
    if function.route is not None:
        db_function.route = function.route
    if function.language is not None:
        db_function.language = function.language
    if function.code is not None:
        db_function.code = function.code
    if function.timeout is not None:
        db_function.timeout = function.timeout
    if function.memory is not None:
        db_function.memory = function.memory
    
    db_function.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(db_function)
    
    # Re-prepare the function in both virtualization technologies
    docker_executor = executor_factory.get_executor("docker")
    gvisor_executor = executor_factory.get_executor("gvisor")
    
    docker_executor.prepare_function(db_function)
    gvisor_executor.prepare_function(db_function)
    
    return db_function

@router.delete("/functions/{function_id}", response_model=Function)
def delete_function(function_id: int, db: Session = Depends(get_db)):
    db_function = db.query(DBFunction).filter(DBFunction.id == function_id).first()
    if db_function is None:
        raise HTTPException(status_code=404, detail="Function not found")
    
    # Remove function from both virtualization technologies
    docker_executor = executor_factory.get_executor("docker")
    gvisor_executor = executor_factory.get_executor("gvisor")
    
    docker_executor.remove_function(db_function)
    gvisor_executor.remove_function(db_function)
    
    db.delete(db_function)
    db.commit()
    
    return db_function

# Function invocation endpoint
@router.post("/functions/{function_id}/invoke", response_model=FunctionInvokeResponse)
def invoke_function(
    function_id: int, 
    virtualization: str = Query("docker", enum=["docker", "gvisor"]),
    invoke_data: FunctionInvoke = Body(default=None), 
    db: Session = Depends(get_db)
):
    db_function = db.query(DBFunction).filter(DBFunction.id == function_id).first()
    if db_function is None:
        raise HTTPException(status_code=404, detail="Function not found")
    
    # Create execution record
    execution = DBExecution(
        function_id=function_id,
        status="running",
        virtualization=virtualization
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    
    # Get appropriate executor
    executor = executor_factory.get_executor(virtualization)
    
    # Execute function
    try:
        start_time = datetime.datetime.utcnow()
        result, metrics = executor.execute_function(
            db_function, 
            invoke_data.parameters if invoke_data else {},
            timeout=db_function.timeout
        )
        end_time = datetime.datetime.utcnow()
        duration = (end_time - start_time).total_seconds() * 1000  # Convert to milliseconds
        
        # Update execution record
        execution.end_time = end_time
        execution.duration = duration
        execution.status = "success"
        execution.memory_used = metrics.get("memory_used_mb", 0)
        execution.cpu_used = metrics.get("cpu_percent", 0)
        db.commit()
        
        # Collect metrics
        metrics_collector.collect(
            function_id=function_id,
            execution_id=execution.id,
            virtualization=virtualization,
            metrics=metrics
        )
        
        return FunctionInvokeResponse(
            result=result,
            execution_id=execution.id,
            duration=duration
        )
    except Exception as e:
        # Update execution record with error
        execution.end_time = datetime.datetime.utcnow()
        execution.duration = (execution.end_time - execution.start_time).total_seconds() * 1000
        execution.status = "error"
        execution.error_message = str(e)
        db.commit()
        
        # Collect error metrics
        metrics_collector.collect(
            function_id=function_id,
            execution_id=execution.id,
            virtualization=virtualization,
            metrics={"duration_ms": execution.duration},
            error=True
        )
        
        raise HTTPException(status_code=500, detail=str(e))

# Execution history endpoints
@router.get("/executions/", response_model=List[Execution])
def read_executions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    executions = db.query(DBExecution).offset(skip).limit(limit).all()
    return executions

@router.get("/functions/{function_id}/executions", response_model=List[Execution])
def read_function_executions(function_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    executions = db.query(DBExecution).filter(DBExecution.function_id == function_id).offset(skip).limit(limit).all()
    return executions

# Metrics endpoints
@router.get("/metrics/functions/{function_id}")
def get_function_metrics(
    function_id: int,
    start_time: Optional[datetime.datetime] = None,
    end_time: Optional[datetime.datetime] = None
):
    return metrics_collector.get_aggregated_metrics(function_id, start_time, end_time)

@router.get("/metrics/compare")
def compare_virtualization_metrics():
    # Get metrics for all functions, grouped by virtualization
    metrics = metrics_collector.get_aggregated_metrics()
    
    # Group by virtualization
    docker_metrics = [m for m in metrics if m["virtualization"] == "docker"]
    gvisor_metrics = [m for m in metrics if m["virtualization"] == "gvisor"]
    
    # Calculate averages
    docker_avg_duration = sum(m["avg_duration_ms"] for m in docker_metrics) / len(docker_metrics) if docker_metrics else 0
    gvisor_avg_duration = sum(m["avg_duration_ms"] for m in gvisor_metrics) / len(gvisor_metrics) if gvisor_metrics else 0
    
    docker_avg_memory = sum(m["avg_memory_used_mb"] for m in docker_metrics) / len(docker_metrics) if docker_metrics else 0
    gvisor_avg_memory = sum(m["avg_memory_used_mb"] for m in gvisor_metrics) / len(gvisor_metrics) if gvisor_metrics else 0
    
    # Return comparison
    return {
        "docker": {
            "avg_duration_ms": docker_avg_duration,
            "avg_memory_used_mb": docker_avg_memory,
            "total_executions": sum(m["total_executions"] for m in docker_metrics),
            "errors": sum(m["errors"] for m in docker_metrics),
        },
        "gvisor": {
            "avg_duration_ms": gvisor_avg_duration,
            "avg_memory_used_mb": gvisor_avg_memory,
            "total_executions": sum(m["total_executions"] for m in gvisor_metrics),
            "errors": sum(m["errors"] for m in gvisor_metrics),
        }
    }