from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import json
import threading
import time

# Create SQLite database engine for metrics
SQLALCHEMY_DATABASE_URL = "sqlite:///./lambda_metrics.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

# Define Metric model
class Metric(Base):
    __tablename__ = "metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    function_id = Column(Integer, index=True)
    execution_id = Column(Integer, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    virtualization = Column(String)  # "docker" or "gvisor"
    duration_ms = Column(Float)
    memory_used_mb = Column(Float)
    cpu_percent = Column(Float)
    is_warm_start = Column(Integer)  # 0 or 1
    error = Column(Integer)  # 0 or 1

# Create all tables
Base.metadata.create_all(bind=engine)

class MetricsCollector:
    def __init__(self):
        self.lock = threading.Lock()
        self.metrics_buffer = []
        self.flush_interval = 10  # seconds
        
        # Start background thread to flush metrics
        self.flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self.flush_thread.start()
    
    def _flush_loop(self):
        """Periodically flush metrics to database"""
        while True:
            time.sleep(self.flush_interval)
            self.flush()
    
    def collect(self, function_id, execution_id, virtualization, metrics, error=False):
        """Collect metrics for a function execution"""
        metric = {
            "function_id": function_id,
            "execution_id": execution_id,
            "timestamp": datetime.datetime.utcnow(),
            "virtualization": virtualization,
            "duration_ms": metrics.get("duration_ms", 0),
            "memory_used_mb": metrics.get("memory_used_mb", 0),
            "cpu_percent": metrics.get("cpu_percent", 0),
            "is_warm_start": 1 if metrics.get("is_warm_start", False) else 0,
            "error": 1 if error else 0
        }
        
        with self.lock:
            self.metrics_buffer.append(metric)
    
    def flush(self):
        """Flush metrics to database"""
        with self.lock:
            if not self.metrics_buffer:
                return
            
            metrics_to_flush = self.metrics_buffer
            self.metrics_buffer = []
        
        # Insert metrics into database
        db = SessionLocal()
        try:
            for metric_data in metrics_to_flush:
                metric = Metric(**metric_data)
                db.add(metric)
            db.commit()
        except Exception as e:
            print(f"Error flushing metrics: {e}")
            db.rollback()
        finally:
            db.close()
    
    def get_function_metrics(self, function_id, start_time=None, end_time=None):
        """Get metrics for a function"""
        db = SessionLocal()
        try:
            query = db.query(Metric).filter(Metric.function_id == function_id)
            
            if start_time:
                query = query.filter(Metric.timestamp >= start_time)
            
            if end_time:
                query = query.filter(Metric.timestamp <= end_time)
            
            return query.all()
        finally:
            db.close()
    
    def get_aggregated_metrics(self, function_id=None, start_time=None, end_time=None):
        """Get aggregated metrics"""
        db = SessionLocal()
        try:
            # Base query
            query = db.query(
                Metric.function_id,
                Metric.virtualization,
                func.avg(Metric.duration_ms).label("avg_duration_ms"),
                func.min(Metric.duration_ms).label("min_duration_ms"),
                func.max(Metric.duration_ms).label("max_duration_ms"),
                func.avg(Metric.memory_used_mb).label("avg_memory_used_mb"),
                func.avg(Metric.cpu_percent).label("avg_cpu_percent"),
                func.sum(Metric.is_warm_start).label("warm_starts"),
                func.count(Metric.id).label("total_executions"),
                func.sum(Metric.error).label("errors")
            )
            
            # Apply filters
            if function_id:
                query = query.filter(Metric.function_id == function_id)
            
            if start_time:
                query = query.filter(Metric.timestamp >= start_time)
            
            if end_time:
                query = query.filter(Metric.timestamp <= end_time)
            
            # Group by function and virtualization
            query = query.group_by(Metric.function_id, Metric.virtualization)
            
            results = query.all()
            
            # Convert to dictionary
            aggregated_metrics = []
            for result in results:
                metrics = {
                    "function_id": result.function_id,
                    "virtualization": result.virtualization,
                    "avg_duration_ms": result.avg_duration_ms,
                    "min_duration_ms": result.min_duration_ms,
                    "max_duration_ms": result.max_duration_ms,
                    "avg_memory_used_mb": result.avg_memory_used_mb,
                    "avg_cpu_percent": result.avg_cpu_percent,
                    "warm_starts": result.warm_starts,
                    "cold_starts": result.total_executions - result.warm_starts,
                    "total_executions": result.total_executions,
                    "errors": result.errors,
                    "success_rate": (result.total_executions - result.errors) / result.total_executions if result.total_executions > 0 else 0
                }
                aggregated_metrics.append(metrics)
            
            return aggregated_metrics
        finally:
            db.close()

# Create singleton instance
metrics_collector = MetricsCollector()