"""Pydantic models for AppPilot Agent communication."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator


class TaskStatus(str, Enum):
    """Task status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Task type enumeration."""
    DEPLOY_TEMPLATE = "deploy_template"
    DEPLOY_COMPOSE = "deploy_compose"
    START_APPLICATION = "start_application"
    STOP_APPLICATION = "stop_application"
    RESTART_APPLICATION = "restart_application"
    DELETE_APPLICATION = "delete_application"


class Task(BaseModel):
    """Task model for agent execution."""
    id: int
    task_uuid: str
    agent_id: str
    task_type: TaskType
    status: TaskStatus
    parameters: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class TaskResult(BaseModel):
    """Task execution result."""
    task_id: int
    agent_id: str
    task_type: TaskType
    success: bool
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    execution_time: Optional[float] = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class ContainerInfo(BaseModel):
    """Docker container information."""
    container_id: str
    name: str
    image: str
    status: str
    ports: Dict[str, str] = Field(default_factory=dict)
    environment: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ServiceInfo(BaseModel):
    """Docker Compose service information."""
    service_name: str
    container_id: Optional[str] = None
    image: str
    status: str
    ports: Dict[str, str] = Field(default_factory=dict)
    environment: Dict[str, str] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)


class DeploymentConfig(BaseModel):
    """Deployment configuration."""
    template_id: int
    app_name: str
    domain: Optional[str] = None
    environment: Dict[str, str] = Field(default_factory=dict)
    volumes: Dict[str, str] = Field(default_factory=dict)
    networks: List[str] = Field(default_factory=list)
    restart_policy: str = "unless-stopped"

    @validator('app_name')
    def validate_app_name(cls, v: str) -> str:
        """Validate application name."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Application name cannot be empty")
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError("Application name can only contain alphanumeric characters, hyphens and underscores")
        return v.strip()


class AgentStatus(BaseModel):
    """Agent status information."""
    agent_id: str
    status: str = "online"
    version: str
    docker_version: Optional[str] = None
    system_info: Dict[str, Any] = Field(default_factory=dict)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    active_deployments: int = 0
    total_deployments: int = 0


class HealthCheck(BaseModel):
    """Health check response."""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str
    uptime: float
    checks: Dict[str, bool] = Field(default_factory=dict)
