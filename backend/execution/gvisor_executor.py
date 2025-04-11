import docker
import tempfile
import os
import json
import time
import threading
from typing import Dict, Any, Tuple

class GVisorExecutor:
    def __init__(self):
        self.client = docker.from_env()
        self.function_images = {}  # Cache of function images
        
    def prepare_function(self, function):
        """Prepare a function for execution by creating a Docker image with gVisor runtime"""
        function_id = function.id
        language = function.language
        code = function.code
        
        # Create a temporary directory to build the Docker image
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create function file
            if language == "python":
                function_file = os.path.join(temp_dir, "function.py")
                with open(function_file, "w") as f:
                    f.write(code)
                
                # Create Dockerfile
                dockerfile = os.path.join(temp_dir, "Dockerfile")
                with open(dockerfile, "w") as f:
                    f.write("""
FROM python:3.9-slim

WORKDIR /app
COPY function.py /app/
COPY wrapper.py /app/

RUN pip install --no-cache-dir psutil

CMD ["python", "wrapper.py"]
                    """)
                
                # Create wrapper script (same as Docker executor)
                wrapper_file = os.path.join(temp_dir, "wrapper.py")
                with open(wrapper_file, "w") as f:
                    f.write("""
import json
import sys
import time
import traceback
import psutil
import os
from function import handler

def main():
    # Read input from environment variable
    input_data = os.environ.get('INPUT_DATA', '{}')
    
    # Parse input
    try:
        event = json.loads(input_data)
    except json.JSONDecodeError:
        event = {}
    
    # Track metrics
    start_time = time.time()
    process = psutil.Process(os.getpid())
    start_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # Execute function
    try:
        result = handler(event)
        status = "success"
        error = None
    except Exception as e:
        result = None
        status = "error"
        error = str(e) + "\\n" + traceback.format_exc()
    
    # Calculate metrics
    end_time = time.time()
    duration = (end_time - start_time) * 1000  # ms
    end_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_used = end_memory - start_memory
    cpu_percent = process.cpu_percent()
    
    # Prepare response
    response = {
        "result": result,
        "status": status,
        "error": error,
        "metrics": {
            "duration_ms": duration,
            "memory_used_mb": memory_used,
            "cpu_percent": cpu_percent
        }
    }
    
    # Write response to stdout
    print(json.dumps(response))

if __name__ == "__main__":
    main()
                    """)
            
            elif language == "javascript":
                function_file = os.path.join(temp_dir, "function.js")
                with open(function_file, "w") as f:
                    f.write(code)
                
                # Create Dockerfile
                dockerfile = os.path.join(temp_dir, "Dockerfile")
                with open(dockerfile, "w") as f:
                    f.write("""
FROM node:16-slim

WORKDIR /app
COPY function.js /app/
COPY wrapper.js /app/

CMD ["node", "wrapper.js"]
                    """)
                
                # Create wrapper script (same as Docker executor)
                wrapper_file = os.path.join(temp_dir, "wrapper.js")
                with open(wrapper_file, "w") as f:
                    f.write("""
const fs = require('fs');
const { handler } = require('./function');

async function main() {
    // Read input from environment variable
    const inputData = process.env.INPUT_DATA || '{}';
    
    // Parse input
    let event;
    try {
        event = JSON.parse(inputData);
    } catch (error) {
        event = {};
    }
    
    // Track metrics
    const startTime = Date.now();
    const startMemory = process.memoryUsage().heapUsed / 1024 / 1024; // MB
    
    // Execute function
    let result, status, error;
    try {
        result = await handler(event);
        status = "success";
        error = null;
    } catch (e) {
        result = null;
        status = "error";
        error = e.stack || e.toString();
    }
    
    // Calculate metrics
    const endTime = Date.now();
    const duration = endTime - startTime; // ms
    const endMemory = process.memoryUsage().heapUsed / 1024 / 1024; // MB
    const memoryUsed = endMemory - startMemory;
    
    // Prepare response
    const response = {
        result,
        status,
        error,
        metrics: {
            duration_ms: duration,
            memory_used_mb: memoryUsed,
            cpu_percent: 0 // Not easily available in Node.js
        }
    };
    
    // Write response to stdout
    console.log(JSON.stringify(response));
}

main().catch(error => {
    console.error('Wrapper error:', error);
    process.exit(1);
});
                    """)
            else:
                raise ValueError(f"Unsupported language: {language}")
            
            # Build Docker image
            image_name = f"lambda-function-gvisor-{function_id}"
            self.client.images.build(path=temp_dir, tag=image_name)
            
            # Store image name
            self.function_images[function_id] = image_name
            
            return image_name
    
    def execute_function(self, function, event={}, timeout=30) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """Execute a function in a Docker container with gVisor runtime"""
        function_id = function.id
        
        # Get or create image
        if function_id not in self.function_images:
            self.prepare_function(function)
        
        image_name = self.function_images[function_id]
        
        # Convert event to JSON
        event_json = json.dumps(event)
        
        # Create container with resource limits and gVisor runtime
        container = self.client.containers.create(
            image=image_name,
            environment={
                "INPUT_DATA": event_json
            },
            mem_limit=f"{function.memory}m",  # Memory limit in MB
            cpu_period=100000,  # CPU period in microseconds
            cpu_quota=100000,   # CPU quota in microseconds (1 CPU core)
            runtime="runsc",    # Use gVisor runtime
            detach=True
        )
        
        # Start container
        start_time = time.time()
        container.start()
        
        # Set up timeout mechanism
        def kill_container():
            try:
                container.kill()
            except:
                pass
        
        timer = threading.Timer(timeout, kill_container)
        timer.start()
        
        try:
            # Wait for container to finish
            result = container.wait(timeout=timeout)
            
            # Cancel timer if container finished before timeout
            timer.cancel()
            
            # Check if container exited successfully
            if result["StatusCode"] != 0:
                logs = container.logs().decode("utf-8")
                raise Exception(f"Function execution failed with status code {result['StatusCode']}: {logs}")
            
            # Get container logs (function output)
            logs = container.logs().decode("utf-8").strip()
            
            # Parse response
            try:
                response = json.loads(logs)
                
                if response["status"] == "error":
                    raise Exception(response["error"])
                
                # Add startup time to metrics
                response["metrics"]["startup_time_ms"] = (time.time() - start_time) * 1000 - response["metrics"]["duration_ms"]
                response["metrics"]["virtualization"] = "gvisor"
                
                return response["result"], response["metrics"]
            except json.JSONDecodeError:
                raise Exception(f"Invalid response from function: {logs}")
        finally:
            # Clean up
            try:
                container.remove(force=True)
            except:
                pass
    
    def remove_function(self, function):
        """Remove a function's Docker image"""
        function_id = function.id
        
        if function_id in self.function_images:
            image_name = self.function_images[function_id]
            
            try:
                self.client.images.remove(image_name)
            except:
                pass
            
            del self.function_images[function_id]