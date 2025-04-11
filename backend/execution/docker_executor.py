import docker
import tempfile
import os
import json
import time
import threading
import uuid
from typing import Dict, Any, Tuple, List
from datetime import datetime, timedelta

class ContainerPool:
    def __init__(self, max_size=10, idle_timeout=300):
        self.max_size = max_size
        self.idle_timeout = idle_timeout  # seconds
        self.containers = {}  # function_id -> list of (container, last_used_time)
        self.lock = threading.Lock()
    
    def get_container(self, function_id, image_name, memory_limit, cpu_quota):
        """Get an available container from the pool or create a new one"""
        with self.lock:
            # Check if we have containers for this function
            if function_id in self.containers and self.containers[function_id]:
                container, _ = self.containers[function_id].pop(0)
                return container, True  # True indicates it's a warm container
            
        # Create a new container
        client = docker.from_env()
        container = client.containers.create(
            image=image_name,
            mem_limit=f"{memory_limit}m",
            cpu_period=100000,
            cpu_quota=cpu_quota,
            detach=True
        )
        
        return container, False  # False indicates it's a cold container
    
    def return_container(self, function_id, container):
        """Return a container to the pool"""
        with self.lock:
            # Initialize container list for this function if it doesn't exist
            if function_id not in self.containers:
                self.containers[function_id] = []
            
            # Check if we have room in the pool
            if len(self.containers[function_id]) < self.max_size:
                # Add container to pool
                self.containers[function_id].append((container, datetime.now()))
                return True
            
            # Pool is full, remove the container
            try:
                container.remove(force=True)
            except:
                pass
            
            return False
    
    def cleanup_idle_containers(self):
        """Remove idle containers from the pool"""
        now = datetime.now()
        with self.lock:
            for function_id in list(self.containers.keys()):
                # Filter out containers that have been idle for too long
                active_containers = []
                for container, last_used in self.containers[function_id]:
                    if now - last_used < timedelta(seconds=self.idle_timeout):
                        active_containers.append((container, last_used))
                    else:
                        try:
                            container.remove(force=True)
                        except:
                            pass
                
                if active_containers:
                    self.containers[function_id] = active_containers
                else:
                    del self.containers[function_id]
    
    def clear(self):
        """Remove all containers from the pool"""
        with self.lock:
            for function_id in list(self.containers.keys()):
                for container, _ in self.containers[function_id]:
                    try:
                        container.remove(force=True)
                    except:
                        pass
                
                del self.containers[function_id]

class DockerExecutor:
    def __init__(self):
        self.client = docker.from_env()
        self.function_images = {}  # Cache of function images
        self.container_pool = ContainerPool(max_size=5, idle_timeout=300)
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
    
    def _cleanup_loop(self):
        """Periodically clean up idle containers"""
        while True:
            time.sleep(60)  # Check every minute
            self.container_pool.cleanup_idle_containers()
    
    def prepare_function(self, function):
        """Prepare a function for execution by creating a Docker image"""
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
                
                # Create wrapper script
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
                
                # Create wrapper script
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
            image_name = f"lambda-function-{function_id}"
            self.client.images.build(path=temp_dir, tag=image_name)
            
            # Store image name
            self.function_images[function_id] = image_name
            
            # Pre-warm the container pool with a few containers
            for _ in range(2):  # Create 2 warm containers
                container = self.client.containers.create(
                    image=image_name,
                    mem_limit=f"{function.memory}m",
                    cpu_period=100000,
                    cpu_quota=100000,
                    detach=True
                )
                self.container_pool.return_container(function_id, container)
            
            return image_name
    
    def execute_function(self, function, event={}, timeout=30) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """Execute a function in a Docker container"""
        function_id = function.id
        
        # Get or create image
        if function_id not in self.function_images:
            self.prepare_function(function)
        
        image_name = self.function_images[function_id]
        
        # Convert event to JSON
        event_json = json.dumps(event)
        
        # Get container from pool or create new one
        container, is_warm = self.container_pool.get_container(
            function_id, 
            image_name, 
            function.memory, 
            100000  # CPU quota
        )
        
        # Track if this is a warm or cold start
        metrics = {"is_warm_start": is_warm}
        
        try:
            # Start container
            container.start()
            
            # Set environment variables
            exec_result = container.exec_run(
                cmd=["sh", "-c", f"export INPUT_DATA='{event_json}'"],
                detach=False
            )
            
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
                    
                    # Merge metrics
                    metrics.update(response["metrics"])
                    
                    return response["result"], metrics
                except json.JSONDecodeError:
                    raise Exception(f"Invalid response from function: {logs}")
            finally:
                # Return container to pool if it's still running
                if container.status == "running":
                    self.container_pool.return_container(function_id, container)
                else:
                    try:
                        container.remove(force=True)
                    except:
                        pass
        except Exception as e:
            # Clean up container on error
            try:
                container.remove(force=True)
            except:
                pass
            raise e
    
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