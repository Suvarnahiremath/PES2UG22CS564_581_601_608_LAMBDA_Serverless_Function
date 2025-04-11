from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

# Create SQLite database engine
SQLALCHEMY_DATABASE_URL = "sqlite:///./lambda_functions.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

# Define Function model
class Function(Base):
    __tablename__ = "functions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    route = Column(String, unique=True, index=True)
    language = Column(String)  # "python" or "javascript"
    code = Column(String)
    timeout = Column(Integer, default=30)  # timeout in seconds
    memory = Column(Integer, default=128)  # memory in MB
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# Define Execution model to store execution history
class Execution(Base):
    __tablename__ = "executions"
    
    id = Column(Integer, primary_key=True, index=True)
    function_id = Column(Integer, index=True)
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)  # in milliseconds
    status = Column(String)  # "success", "error", "timeout"
    error_message = Column(String, nullable=True)
    virtualization = Column(String)  # "docker", "firecracker", etc.
    memory_used = Column(Float, nullable=True)  # in MB
    cpu_used = Column(Float, nullable=True)  # percentage

# Create all tables
def create_tables():
    Base.metadata.create_all(bind=engine)

# Get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    create_tables()
    print("Database tables created successfully")