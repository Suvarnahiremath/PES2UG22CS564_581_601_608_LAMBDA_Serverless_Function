from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import sys
import os
# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)
from backend.api.routes import router as api_router
from backend.database.db import create_tables

app = FastAPI(title="Serverless Function Platform")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")

# Create database tables
create_tables()

# Dynamic function routing
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def dynamic_function_route(request: Request, path: str):
    from sqlalchemy.orm import Session
    from .database.db import SessionLocal, Function
    from .execution.docker_executor import DockerExecutor
    
    # Get database session
    db = SessionLocal()
    try:
        # Find function by route
        function = db.query(Function).filter(Function.route == f"/{path}").first()
        
        if not function:
            return Response(
                content=json.dumps({"error": "Function not found"}),
                status_code=404,
                media_type="application/json"
            )
        
        # Parse request body
        try:
            body = await request.json()
        except:
            body = {}
        
        # Execute function
        executor = DockerExecutor()
        result, _ = executor.execute_function(function, body, timeout=function.timeout)
        
        # Return result
        return Response(
            content=json.dumps(result),
            status_code=200,
            media_type="application/json"
        )
    finally:
        db.close()

if __name__ == "__main__":
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)