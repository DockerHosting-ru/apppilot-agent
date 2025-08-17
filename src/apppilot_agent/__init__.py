"""AppPilot Agent - Docker Compose deployment agent."""

__version__ = "0.1.0"
__author__ = "AppPilot Team"
__email__ = "team@apppilot.dev"

from .agent import AppPilotAgent
from .models import Task, TaskResult, DeploymentConfig

__all__ = ["AppPilotAgent", "Task", "TaskResult", "DeploymentConfig"]
