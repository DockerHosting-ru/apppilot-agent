
#!/usr/bin/env python3
"""
AppPilot Agent with Docker Compose support for multi-container applications
"""

import os
import sys
import time
import signal
import logging
import subprocess
import requests
import docker
import socket
import random
import uuid
import yaml
import shutil
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('appliku-agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AppPilotAgentCompose:
    def __init__(self, server_url: str, agent_token: str, agent_id: str, 
                 apps_dir: str = "apps", logs_dir: str = "logs"):
        """
        Initialize agent with Docker Compose support
        
        Args:
            server_url: API server URL
            agent_token: Authentication token
            agent_id: Unique agent identifier
            apps_dir: Directory for applications
            logs_dir: Directory for logs
        """
        self.server_url = server_url.rstrip('/')
        self.agent_token = agent_token
        self.agent_id = agent_id
        self.running = False
        self.docker_client = None
        
        # API request headers
        self.headers = {
            'Authorization': f'Bearer {agent_token}',
            'Content-Type': 'application/json',
            'X-Agent-ID': agent_id
        }
        
        logger.info(f"Initializing AppPilot agent with Docker Compose support: {agent_id}")
        logger.info(f"Server URL: {server_url}")
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            # Test Docker connection
            self.docker_client.ping()
            logger.info("Docker client connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            self.docker_client = None
        
        # Create directories
        self.apps_dir = Path(apps_dir)
        self.logs_dir = Path(logs_dir)
        self.apps_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # Port range for applications
        self.port_range_start = 8001
        self.port_range_end = 9000
        
        # Compose templates for multi-container applications
        self.compose_templates = {
            '100': {
                'name': 'n8n with PostgreSQL',
                'template_dir': '100-n8n-postgres',
                'main_service': 'n8n',
                'services': ['postgres', 'n8n'],
                'stack_name': 'n8n-postgres-stack'
            },
            '101': {
                'name': 'WordPress with MySQL',
                'template_dir': '101-wordpress-mysql',
                'main_service': 'wordpress',
                'services': ['mysql', 'wordpress'],
                'stack_name': 'wordpress-mysql-stack'
            },
            '102': {
                'name': 'Nextcloud with PostgreSQL',
                'template_dir': '102-nextcloud-postgres',
                'main_service': 'nextcloud',
                'services': ['postgres', 'nextcloud'],
                'stack_name': 'nextcloud-postgres-stack'
            }
        }

    def start(self) -> None:
        """Start the agent"""
        logger.info("Starting AppPilot agent with Docker Compose support")
        self.running = True
        
        # Register agent
        if self._register_agent():
            logger.info("Agent registered successfully")
        else:
            logger.error("Failed to register agent")
            return
        
        # Main command processing loop
        while self.running:
            try:
                self._process_commands()
                time.sleep(5)  # Poll every 5 seconds
            except KeyboardInterrupt:
                logger.info("Received stop signal")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(10)
        
        logger.info("Agent stopped")

    def _register_agent(self) -> bool:
        """Register agent with the server"""
        try:
            registration_data = {
                "agent_id": self.agent_id,
                "agent_version": "2.0.0-compose",
                "system_info": {
                    "os": "linux",
                    "docker_version": self._get_docker_version(),
                    "compose_support": True,
                    "capabilities": ["docker", "compose"]
                }
            }
            
            # Headers for registration WITHOUT authentication
            registration_headers = {
                'Content-Type': 'application/json',
                'X-Agent-ID': self.agent_id
            }
            
            response = requests.post(
                f"{self.server_url}/api2/appliku/vps/register-agent",
                json=registration_data,
                headers=registration_headers,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info("Agent successfully registered")
                return True
            else:
                logger.error(f"Registration error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error during agent registration: {e}")
            return False

    def _get_docker_version(self) -> str:
        """Get Docker version"""
        try:
            if self.docker_client:
                version = self.docker_client.version()
                return version.get('Version', 'unknown')
        except:
            pass
        return 'unknown'

    def _process_commands(self):
        """Process commands from the server"""
        try:
            response = requests.get(
                f"{self.server_url}/api2/appliku/vps/commands?agent_id={self.agent_id}",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                commands = response.json()
                
                # API returns a list of tasks directly
                if isinstance(commands, list):
                    for command in commands:
                        self._execute_command(command)
                else:
                    # If it comes wrapped
                    tasks = commands.get('tasks', [])
                    for command in tasks:
                        self._execute_command(command)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting commands: {e}")
        except Exception as e:
            logger.error(f"Error processing commands: {e}")

    def _execute_command(self, command: Dict[str, Any]):
        """Execute a command"""
        command_id = command.get('id')
        task_type = command.get('task_type')
        data = command.get('data', {})
        
        logger.info(f"Executing command {command_id}: {task_type}")
        
        try:
            if task_type == 'deploy_template' or task_type == 'deploy_compose':
                template_id = data.get('template_id')
                
                # Determine deployment type
                if template_id in self.compose_templates or task_type == 'deploy_compose':
                    logger.info(f"Deploying compose template {template_id}")
                    result = self._deploy_compose_template(data)
                else:
                    logger.info(f"Deploying single-container template {template_id}")
                    result = self._deploy_single_template(data)
                
                # Send result
                self._send_command_result(command_id, result, task_type)
                
            elif task_type == 'deploy_git':
                logger.info(f"Deploying application from Git repository")
                result = self._deploy_git_repository(data)
                self._send_command_result(command_id, result, task_type)
                
                # Send result
                self._send_command_result(command_id, result, task_type)
                
            elif task_type == 'stop_application':
                result = self._stop_application(data)
                self._send_command_result(command_id, result, task_type)
                
            elif task_type == 'restart_application':
                result = self._restart_application(data)
                self._send_command_result(command_id, result, task_type)
                
            elif task_type == 'delete_application':
                result = self._delete_application(data)
                self._send_command_result(command_id, result, task_type)
                
            else:
                logger.warning(f"Unknown command type: {task_type}")
                
        except Exception as e:
            logger.error(f"Error executing command {command_id}: {e}")
            self._send_command_result(command_id, {'error': str(e)}, task_type)

    def _get_template_path(self, template_dir: str) -> Path:
        """Get template path for Docker Compose files"""
        # Look for templates in current directory first
        current_templates = Path("templates") / "compose" / template_dir
        if current_templates.exists():
            return current_templates / "docker-compose.yml"
        
        # Fallback to absolute path
        return Path("/root/agent/templates/compose") / template_dir / "docker-compose.yml"

    def _deploy_compose_template(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Deploy multi-container application via Docker Compose"""
        try:
            template_id = data.get('template_id')
            app_id = data.get('app_id')
            
            template_config = self.compose_templates.get(template_id)
            if not template_config:
                return {'error': f'Template {template_id} not found'}
            
            logger.info(f"Deploying {template_config['name']} for application {app_id}")
            
            # Find a free port
            external_port = self._find_free_port()
            if not external_port:
                return {'error': 'No free ports available'}
            
            # Prepare directory for deployment
            app_dir = self.apps_dir / app_id
            app_dir.mkdir(exist_ok=True)
            
            # Prepare variables for substitution
            env_vars = {
                'APP_ID': app_id,
                'TEMPLATE_ID': template_id,
                'EXTERNAL_PORT': str(external_port),
                'SERVER_IP': self._get_server_ip(),
                'STACK_NAME': template_config['stack_name']
            }
            
            # Read template and substitute variables
            template_path = self._get_template_path(template_config['template_dir'])
            compose_path = app_dir / "docker-compose.yml"
            
            if not compose_path.exists():
                return {'error': f'Template file not found: {compose_path}'}
            
            # Read template file
            with open(compose_path, 'r') as f:
                template_content = f.read()
            
            # Substitute variables
            for key, value in env_vars.items():
                template_content = template_content.replace(f"${{{key}}}", str(value))
            
            # Write the ready docker-compose.yml
            with open(compose_path, 'w') as f:
                f.write(template_content)
            
            # Add user environment variables
            user_env = data.get('environment_vars', {})
            env_vars.update(user_env)
            
            env_file_path = app_dir / ".env"
            with open(env_file_path, 'w') as f:
                for key, value in env_vars.items():
                    f.write(f"{key}={value}\n")
            
            logger.info(f"Created .env file: {env_file_path}")
            
            # Start docker-compose up
            logger.info(f"Starting docker-compose in {app_dir}")
            
            result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd=app_dir,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.info(f"Docker Compose successfully started")
            logger.info(f"Stdout: {result.stdout}")
            
            # Get information about created containers
            containers_info = self._get_compose_containers_info(app_id, template_config)
            
            return {
                'success': True,
                'result': {
                    'app_type': 'compose',
                    'template_id': template_id,
                    'template_name': template_config['name'],
                    'external_port': external_port,
                    'stack_name': template_config['stack_name'],
                    'main_service': template_config['main_service'],
                    'containers': containers_info,
                    'app_url': f"http://{self._get_server_ip()}:{external_port}",
                    'status': 'running'
                }
            }
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Docker Compose error: {e.stderr}")
            return {'error': f'Docker Compose failed: {e.stderr}'}
        except Exception as e:
            logger.error(f"Error deploying Compose: {e}")
            return {'error': str(e)}

    def _get_compose_containers_info(self, app_id: str, template_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get information about Compose application containers"""
        containers_info = []
        
        try:
            # Search for containers by prefix (more reliable)
            all_containers = self.docker_client.containers.list()
            
            for container in all_containers:
                container_name = container.name
                
                # Check if the container belongs to our application
                if container_name.startswith(f"{app_id}-"):
                    # Determine service_name from container name
                    service_name = container_name.replace(f"{app_id}-", "").split('-')[0]
                    
                    # Check if it's a known service
                    if service_name in template_config['services']:
                        containers_info.append({
                            'service_name': service_name,
                            'container_id': container.id,
                            'container_name': container_name,
                            'status': container.status,
                            'is_main_service': service_name == template_config['main_service']
                        })
                        logger.info(f"Found container: {container_name} (service: {service_name})")
                    
        except Exception as e:
            logger.error(f"Error getting container information: {e}")
        
        return containers_info

    def _deploy_single_template(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Deploy single-container application (old logic)"""
        try:
            app_id = data.get('app_id')
            template_id = data.get('template_id')
            
            # Configurations for single-container templates
            template_configs = {
                '1': {'image': 'nginx:alpine', 'default_port': 80, 'name': 'Nginx'},
                '2': {'image': 'httpd:alpine', 'default_port': 80, 'name': 'Apache'}, 
                '3': {'image': 'node:18-alpine', 'default_port': 3000, 'name': 'Node.js'},
                '4': {'image': 'n8nio/n8n:latest', 'default_port': 5678, 'name': 'n8n'},  # Keep for compatibility
                '5': {'image': 'python:3.11-slim', 'default_port': 8000, 'name': 'Python HTTP Server'}
            }
            
            template_config = template_configs.get(template_id)
            if not template_config:
                return {'error': f'Unknown template_id: {template_id}'}
            
            logger.info(f"Deploying {template_config['name']} for application {app_id}")
            
            # Find a free port
            external_port = self._find_free_port()
            if not external_port:
                return {'error': 'No free ports available'}
            
            image_name = template_config['image']
            internal_port = template_config['default_port']
            container_name = f"appliku-app_{app_id}"
            
            # Prepare environment variables
            environment = data.get('environment_vars', {})
            
            # Special command for Python HTTP Server
            container_command = None
            if template_id == '5':  # Python HTTP Server
                container_command = ['python', '-m', 'http.server', '8000']
                internal_port = 8000
            
            logger.info(f"Starting container {container_name}")
            logger.info(f"Image: {image_name}")
            logger.info(f"Ports: {internal_port} -> {external_port}")
            
            # Start container
            container_args = {
                'image': image_name,
                'detach': True,
                'name': container_name,
                'ports': {internal_port: external_port},
                'environment': environment,
                'restart_policy': {'Name': 'unless-stopped'},
                'labels': {
                    'appliku.app_id': app_id,
                    'appliku.template_id': str(template_id),
                    'appliku.managed': 'true'
                }
            }
            
            # Add command if specified
            if container_command:
                container_args['command'] = container_command
            
            container = self.docker_client.containers.run(**container_args)
            
            # Wait for container to start
            time.sleep(2)
            container.reload()
            
            if container.status == 'running':
                logger.info(f"Container {container_name} successfully started")
                
                return {
                    'success': True,
                    'result': {
                        'app_type': 'single',
                        'container_id': container.id,
                        'container_name': container_name,
                        'external_port': external_port,
                        'app_url': f"http://{self._get_server_ip()}:{external_port}",
                        'status': 'running',
                        'template_name': template_config['name']
                    }
                }
            else:
                logger.error(f"Container failed to start: {container.status}")
                return {'error': f'Container failed to start: {container.status}'}
                
        except Exception as e:
            logger.error(f"Error deploying single template: {e}")
            return {'error': str(e)}

    def _find_free_port(self) -> Optional[int]:
        """Find a free port in the range"""
        try:
            # Get list of used ports from Docker
            used_ports = set()
            
            for container in self.docker_client.containers.list():
                ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
                for port_binding in ports.values():
                    if port_binding:
                        for binding in port_binding:
                            if binding.get('HostPort'):
                                used_ports.add(int(binding['HostPort']))
            
            # Find a free port
            for port in range(self.port_range_start, self.port_range_end + 1):
                if port not in used_ports:
                    # Additional check via socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        sock.bind(('0.0.0.0', port))
                        sock.close()
                        logger.info(f"Found free port: {port}")
                        return port
                    except OSError:
                        continue
                    finally:
                        sock.close()
            
            logger.error("No free ports in the range")
            return None
            
        except Exception as e:
            logger.error(f"Error finding free port: {e}")
            return None

    def _get_server_ip(self) -> str:
        """Get server IP address"""
        try:
            # Try to get external IP
            response = requests.get('http://httpbin.org/ip', timeout=5)
            if response.status_code == 200:
                return response.json().get('origin', 'localhost')
        except:
            pass
        
        # Fallback to local IP
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            return ip
        except:
            return 'localhost'

    def _send_command_result(self, command_id: str, result: Dict[str, Any], task_type: str = 'unknown'):
        """Send command execution result"""
        try:
            result_data = {
                'task_id': command_id,
                'agent_id': self.agent_id,
                'task_type': task_type,
                'success': 'error' not in result,
                'result': result,
                'execution_time': 5.0  # time in seconds
            }
            
            # Use the same headers format as for getting commands
            result_headers = {
                'Authorization': f'Bearer {self.agent_token}',
                'Content-Type': 'application/json',
                'X-Agent-ID': self.agent_id
            }
            
            logger.info(f"Sending command result {command_id}: {result_data}")
            
            response = requests.post(
                f"{self.server_url}/api2/appliku/vps/command-result",
                json=result_data,
                headers=result_headers,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Command {command_id} result sent successfully")
            else:
                logger.error(f"Error sending result: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending command result: {e}")

    def _deploy_git_repository(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Deploy application from Git repository"""
        try:
            app_id = data.get('app_id')
            git_url = data.get('git_url')
            branch = data.get('branch', 'main')
            app_type = data.get('app_type', 'auto')
            
            logger.info(f"Deploying application {app_id} from {git_url}")
            
            if not git_url:
                return {'error': 'Git URL not specified'}
            
            # Find a free port
            external_port = self._find_free_port()
            if not external_port:
                return {'error': 'No free ports'}
            
            # Create application directory
            app_dir = self.apps_dir / app_id
            app_dir.mkdir(exist_ok=True)
            
            # Clone repository
            logger.info(f"Cloning {git_url} (branch: {branch})")
            clone_cmd = f"cd {app_dir} && git clone -b {branch} {git_url} ."
            result = subprocess.run(clone_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                return {'error': f'Error cloning: {result.stderr}'}
            
            # Determine application type if auto
            if app_type == 'auto':
                app_type = self._detect_app_type(app_dir)
            
            # Create Dockerfile if it doesn't exist
            dockerfile_path = app_dir / "Dockerfile"
            if not dockerfile_path.exists():
                dockerfile_content = self._generate_dockerfile(app_type, external_port)
                with open(dockerfile_path, 'w') as f:
                    f.write(dockerfile_content)
                logger.info(f"Created Dockerfile for {app_type}")
            
            # Build image
            image_name = f"appliku-app-{app_id}"
            logger.info(f"Building image {image_name}")
            
            image, logs = self.docker_client.images.build(
                path=app_dir,
                tag=image_name,
                rm=True
            )
            
            # Stop existing container
            container_name = f"appliku-{app_id}"
            try:
                existing = self.docker_client.containers.get(container_name)
                existing.stop()
                existing.remove()
                logger.info(f"Stopped existing container: {container_name}")
            except docker.errors.NotFound:
                pass
            
            # Start container
            container = self.docker_client.containers.run(
                image_name,
                detach=True,
                name=container_name,
                ports={external_port: external_port},
                restart_policy={'Name': 'unless-stopped'},
                labels={
                    'appliku.app_id': app_id,
                    'appliku.managed': 'true',
                    'appliku.type': 'git'
                }
            )
            
            time.sleep(3)
            container.reload()
            
            if container.status == 'running':
                app_url = f"http://{self._get_server_ip()}:{external_port}"
                
                return {
                    'success': True,
                    'result': {
                        'app_type': 'git',
                        'container_id': container.id,
                        'container_name': container_name,
                        'external_port': external_port,
                        'app_url': app_url,
                        'git_url': git_url,
                        'branch': branch,
                        'app_type_detected': app_type,
                        'status': 'running'
                    }
                }
            else:
                return {'error': f'Container failed to start. Status: {container.status}'}
            
        except Exception as e:
            logger.error(f"Error Git deployment: {e}")
            return {'error': str(e)}

    def _detect_app_type(self, app_dir: Path) -> str:
        """Determine application type"""
        if (app_dir / 'package.json').exists():
            return 'node'
        elif (app_dir / 'requirements.txt').exists():
            return 'python'
        elif (app_dir / 'composer.json').exists():
            return 'php'
        elif (app_dir / 'go.mod').exists():
            return 'go'
        else:
            return 'static'

    def _generate_dockerfile(self, app_type: str, port: int) -> str:
        """Generate Dockerfile for different application types"""
        dockerfiles = {
            'node': f'''FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE {port}
CMD ["npm", "start"]''',
            'python': f'''FROM python:3.9-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE {port}
CMD ["python", "app.py"]''',
            'php': f'''FROM php:8.1-apache
COPY . /var/www/html/
EXPOSE 80''',
            'static': f'''FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE 80'''
        }
        
        return dockerfiles.get(app_type, dockerfiles['static'])

    def _stop_application(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Stop application"""
        try:
            app_id = data.get('app_id')
            logger.info(f"Stopping application {app_id}")
            
            # Find application containers
            containers = self.docker_client.containers.list(
                filters={'label': f'appliku.app_id={app_id}'}
            )
            
            if not containers:
                return {'error': f'No containers found for app {app_id}'}
            
            stopped_containers = []
            for container in containers:
                container.stop()
                stopped_containers.append(container.name)
                logger.info(f"Stopped container: {container.name}")
            
            return {
                'success': True,
                'result': {
                    'stopped_containers': stopped_containers,
                    'status': 'stopped'
                }
            }
            
        except Exception as e:
            logger.error(f"Error stopping application: {e}")
            return {'error': str(e)}

    def _restart_application(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Restart application"""
        try:
            app_id = data.get('app_id')
            logger.info(f"Restarting application {app_id}")
            
            # Find application containers
            containers = self.docker_client.containers.list(
                all=True,
                filters={'label': f'appliku.app_id={app_id}'}
            )
            
            if not containers:
                return {'error': f'No containers found for app {app_id}'}
            
            restarted_containers = []
            for container in containers:
                container.restart()
                restarted_containers.append(container.name)
                logger.info(f"Restarted container: {container.name}")
            
            return {
                'success': True,
                'result': {
                    'restarted_containers': restarted_containers,
                    'status': 'running'
                }
            }
            
        except Exception as e:
            logger.error(f"Error restarting application: {e}")
            return {'error': str(e)}

    def _delete_application(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Delete application"""
        try:
            app_id = data.get('app_id')
            logger.info(f"Deleting application {app_id}")
            
            # Find application containers
            containers = self.docker_client.containers.list(
                all=True,
                filters={'label': f'appliku.app_id={app_id}'}
            )
            
            if not containers:
                return {'error': f'No containers found for app {app_id}'}
            
            removed_containers = []
            for container in containers:
                container.remove()
                removed_containers.append(container.name)
                logger.info(f"Removed container: {container.name}")
            
            # Delete application directory
            app_dir = self.apps_dir / app_id
            if app_dir.exists():
                shutil.rmtree(app_dir)
                logger.info(f"Deleted directory: {app_dir}")
            
            return {
                'success': True,
                'result': {
                    'removed_containers': removed_containers,
                    'status': 'deleted'
                }
            }
            
        except Exception as e:
            logger.error(f"Error deleting application: {e}")
            return {'error': str(e)}

def main():
    """Main function"""
    # Get settings from environment variables
    server_url = os.getenv('APPLIKU_SERVER_URL', 'http://31.169.124.43:8000')
    agent_token = os.getenv('APPLIKU_AGENT_TOKEN', 'test-agent-token-001')
    agent_id = os.getenv('APPLIKU_AGENT_ID', 'test-agent-001')
    
    logger.info(f"Starting AppPilot agent with Compose support")
    logger.info(f"Agent ID: {agent_id}")
    logger.info(f"Server: {server_url}")
    
    # Create and start agent
    agent = AppPilotAgentCompose(server_url, agent_token, agent_id)
    
    # Signal handling for graceful termination
    def signal_handler(signum, frame):
        logger.info("Received stop signal")
        agent.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        agent.start()
    except Exception as e:
        logger.error(f"Critical agent error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
