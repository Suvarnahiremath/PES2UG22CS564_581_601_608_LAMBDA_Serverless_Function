from .docker_executor import DockerExecutor
from .gvisor_executor import GVisorExecutor

class ExecutorFactory:
    def __init__(self):
        self.docker_executor = DockerExecutor()
        self.gvisor_executor = GVisorExecutor()
    
    def get_executor(self, virtualization_type):
        """Get the appropriate executor based on virtualization type"""
        if virtualization_type == "docker":
            return self.docker_executor
        elif virtualization_type == "gvisor":
            return self.gvisor_executor
        else:
            raise ValueError(f"Unsupported virtualization type: {virtualization_type}")