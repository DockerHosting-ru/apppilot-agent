#!/usr/bin/env python3
"""
Агент Appliku с поддержкой Docker Compose для multi-container приложений
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
from typing import Dict, Any, List, Optional
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/appliku/logs/appliku-agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ApplikuAgentCompose:
    def __init__(self, server_url: str, agent_token: str, agent_id: str):
        """
        Инициализация агента с поддержкой Docker Compose
        """
        self.server_url = server_url.rstrip('/')
        self.agent_token = agent_token
        self.agent_id = agent_id
        self.running = False
        self.docker_client = None
        
        # Заголовки для API запросов
        self.headers = {
            'Authorization': f'Bearer {agent_token}',
            'Content-Type': 'application/json',
            'X-Agent-ID': agent_id
        }
        
        logger.info(f"🚀 Инициализация агента с Docker Compose поддержкой: {agent_id}")
        logger.info(f"🌐 Server URL: {server_url}")
        
        # Инициализация Docker клиента
        try:
            self.docker_client = docker.from_env()
            # Проверяем подключение к Docker
            self.docker_client.ping()
            logger.info("✅ Docker клиент подключен успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Docker: {e}")
            self.docker_client = None
        
        # Создаем директории
        os.makedirs('/opt/appliku/apps', exist_ok=True)
        os.makedirs('/opt/appliku/logs', exist_ok=True)
        
        # Диапазон портов для приложений
        self.port_range_start = 8001
        self.port_range_end = 9000
        
        # Compose шаблоны для multi-container приложений
        self.compose_templates = {
            '100': {
                'name': 'n8n с PostgreSQL',
                'template_dir': '100-n8n-postgres',
                'main_service': 'n8n',
                'services': ['postgres', 'n8n'],
                'stack_name': 'n8n-postgres-stack'
            },
            '101': {
                'name': 'WordPress с MySQL',
                'template_dir': '101-wordpress-mysql',
                'main_service': 'wordpress',
                'services': ['mysql', 'wordpress'],
                'stack_name': 'wordpress-mysql-stack'
            },
            '102': {
                'name': 'Nextcloud с PostgreSQL',
                'template_dir': '102-nextcloud-postgres',
                'main_service': 'nextcloud',
                'services': ['postgres', 'nextcloud'],
                'stack_name': 'nextcloud-postgres-stack'
            }
        }

    def start(self):
        """Запуск агента"""
        logger.info("🎯 Запуск агента с Docker Compose поддержкой")
        self.running = True
        
        # Регистрируем агент
        if self._register_agent():
            logger.info("✅ Агент зарегистрирован")
        else:
            logger.error("❌ Ошибка регистрации агента")
            return
        
        # Основной цикл обработки команд
        while self.running:
            try:
                self._process_commands()
                time.sleep(5)  # Опрос каждые 5 секунд
            except KeyboardInterrupt:
                logger.info("🛑 Получен сигнал остановки")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в основном цикле: {e}")
                time.sleep(10)
        
        logger.info("🔚 Агент остановлен")

    def _register_agent(self) -> bool:
        """Регистрация агента на сервере"""
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
            
            # Заголовки для регистрации БЕЗ авторизации
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
                logger.info("✅ Агент успешно зарегистрирован")
                return True
            else:
                logger.error(f"❌ Ошибка регистрации: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка при регистрации агента: {e}")
            return False

    def _get_docker_version(self) -> str:
        """Получение версии Docker"""
        try:
            if self.docker_client:
                version = self.docker_client.version()
                return version.get('Version', 'unknown')
        except:
            pass
        return 'unknown'

    def _process_commands(self):
        """Обработка команд от сервера"""
        try:
            response = requests.get(
                f"{self.server_url}/api2/appliku/vps/commands?agent_id={self.agent_id}",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                commands = response.json()
                
                # API возвращает список задач напрямую
                if isinstance(commands, list):
                    for command in commands:
                        self._execute_command(command)
                else:
                    # Если приходит в обертке
                    tasks = commands.get('tasks', [])
                    for command in tasks:
                        self._execute_command(command)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка получения команд: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки команд: {e}")

    def _execute_command(self, command: Dict[str, Any]):
        """Выполнение команды"""
        command_id = command.get('id')
        task_type = command.get('task_type')
        data = command.get('data', {})
        
        logger.info(f"🎯 Выполнение команды {command_id}: {task_type}")
        
        try:
            if task_type == 'deploy_template' or task_type == 'deploy_compose':
                template_id = data.get('template_id')
                
                # Определяем тип развертывания
                if template_id in self.compose_templates or task_type == 'deploy_compose':
                    logger.info(f"🐳 Compose развертывание template {template_id}")
                    result = self._deploy_compose_template(data)
                else:
                    logger.info(f"📦 Single-container развертывание template {template_id}")
                    result = self._deploy_single_template(data)
                
                # Отправляем результат
                self._send_command_result(command_id, result, task_type)
                
            elif task_type == 'deploy_git':
                logger.info(f"📥 Git развертывание приложения")
                result = self._deploy_git_repository(data)
                self._send_command_result(command_id, result, task_type)
                
            elif task_type == 'deploy_application':
                logger.info(f"📥 Развертывание приложения из Git")
                result = self._deploy_git_repository(data)
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
                
            elif task_type == 'get_container_logs':
                result = self._get_container_logs(data)
                self._send_command_result(command_id, result, task_type)
                
            else:
                logger.warning(f"⚠️ Неизвестный тип команды: {task_type}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения команды {command_id}: {e}")
            self._send_command_result(command_id, {'error': str(e)}, task_type)

    def _deploy_compose_template(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Развертывание multi-container приложения через Docker Compose"""
        try:
            template_id = data.get('template_id')
            app_id = data.get('app_id')
            
            template_config = self.compose_templates.get(template_id)
            if not template_config:
                return {'error': f'Template {template_id} not found'}
            
            logger.info(f"🚀 Разворачиваем {template_config['name']} для приложения {app_id}")
            
            # Находим свободный порт
            external_port = self._find_free_port()
            if not external_port:
                return {'error': 'No free ports available'}
            
            # Подготавливаем директорию для развертывания
            app_dir = f"/opt/appliku/apps/{app_id}"
            os.makedirs(app_dir, exist_ok=True)
            
            # Подготавливаем переменные для подстановки
            env_vars = {
                'APP_ID': app_id,
                'TEMPLATE_ID': template_id,
                'EXTERNAL_PORT': str(external_port),
                'SERVER_IP': self._get_server_ip(),
                'STACK_NAME': template_config['stack_name']
            }
            
            # Читаем шаблон и подставляем переменные
            template_path = f"/root/agent/templates/compose/{template_config['template_dir']}/docker-compose.yml"
            compose_path = f"{app_dir}/docker-compose.yml"
            
            if not os.path.exists(template_path):
                return {'error': f'Template file not found: {template_path}'}
            
            # Читаем шаблон файл
            with open(template_path, 'r') as f:
                template_content = f.read()
            
            # Подставляем переменные
            for key, value in env_vars.items():
                template_content = template_content.replace(f"${{{key}}}", str(value))
            
            # Записываем готовый docker-compose.yml
            with open(compose_path, 'w') as f:
                f.write(template_content)
            
            # Добавляем пользовательские переменные окружения
            user_env = data.get('environment_vars', {})
            env_vars.update(user_env)
            
            env_file_path = f"{app_dir}/.env"
            with open(env_file_path, 'w') as f:
                for key, value in env_vars.items():
                    f.write(f"{key}={value}\n")
            
            logger.info(f"📝 Создан .env файл: {env_file_path}")
            
            # Запускаем docker-compose up
            logger.info(f"🐳 Запускаем docker-compose в {app_dir}")
            
            result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd=app_dir,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.info(f"✅ Docker Compose успешно запущен")
            logger.info(f"📋 Stdout: {result.stdout}")
            
            # Получаем информацию о созданных контейнерах
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
            logger.error(f"❌ Docker Compose ошибка: {e.stderr}")
            return {'error': f'Docker Compose failed: {e.stderr}'}
        except Exception as e:
            logger.error(f"❌ Ошибка развертывания Compose: {e}")
            return {'error': str(e)}

    def _get_compose_containers_info(self, app_id: str, template_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение информации о контейнерах Compose приложения"""
        containers_info = []
        
        try:
            # Ищем контейнеры по префиксу имени (более надежно)
            all_containers = self.docker_client.containers.list()
            
            for container in all_containers:
                container_name = container.name
                
                # Проверяем, относится ли контейнер к нашему приложению
                if container_name.startswith(f"{app_id}-"):
                    # Определяем service_name из имени контейнера
                    service_name = container_name.replace(f"{app_id}-", "").split('-')[0]
                    
                    # Проверяем, что это известный сервис
                    if service_name in template_config['services']:
                        containers_info.append({
                            'service_name': service_name,
                            'container_id': container.id,
                            'container_name': container_name,
                            'status': container.status,
                            'is_main_service': service_name == template_config['main_service']
                        })
                        logger.info(f"📦 Найден контейнер: {container_name} (сервис: {service_name})")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о контейнерах: {e}")
        
        return containers_info

    def _deploy_single_template(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Развертывание single-container приложения (старая логика)"""
        try:
            app_id = data.get('app_id')
            template_id = data.get('template_id')
            
            # Конфигурации для single-container шаблонов
            template_configs = {
                '1': {'image': 'nginx:alpine', 'default_port': 80, 'name': 'Nginx'},
                '2': {'image': 'httpd:alpine', 'default_port': 80, 'name': 'Apache'}, 
                '3': {'image': 'node:18-alpine', 'default_port': 3000, 'name': 'Node.js'},
                '4': {'image': 'n8nio/n8n:latest', 'default_port': 5678, 'name': 'n8n'},  # Пока оставляем для совместимости
                '5': {'image': 'python:3.11-slim', 'default_port': 8000, 'name': 'Python HTTP Server'}
            }
            
            template_config = template_configs.get(template_id)
            if not template_config:
                return {'error': f'Unknown template_id: {template_id}'}
            
            logger.info(f"🚀 Разворачиваем {template_config['name']} для приложения {app_id}")
            
            # Находим свободный порт
            external_port = self._find_free_port()
            if not external_port:
                return {'error': 'No free ports available'}
            
            image_name = template_config['image']
            internal_port = template_config['default_port']
            container_name = f"appliku-app_{app_id}"
            
            # Подготовка environment variables
            environment = data.get('environment_vars', {})
            
            # Специальная команда для Python HTTP Server
            container_command = None
            if template_id == '5':  # Python HTTP Server
                container_command = ['python', '-m', 'http.server', '8000']
                internal_port = 8000
            
            logger.info(f"🎯 Запуск контейнера {container_name}")
            logger.info(f"🖼️ Образ: {image_name}")
            logger.info(f"🔌 Порты: {internal_port} -> {external_port}")
            
            # Запускаем контейнер
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
            
            # Добавляем команду если указана
            if container_command:
                container_args['command'] = container_command
            
            container = self.docker_client.containers.run(**container_args)
            
            # Ждем запуска контейнера
            time.sleep(2)
            container.reload()
            
            if container.status == 'running':
                logger.info(f"✅ Контейнер {container_name} успешно запущен")
                
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
                logger.error(f"❌ Контейнер не запустился: {container.status}")
                return {'error': f'Container failed to start: {container.status}'}
                
        except Exception as e:
            logger.error(f"❌ Ошибка развертывания single template: {e}")
            return {'error': str(e)}

    def _find_free_port(self) -> Optional[int]:
        """Поиск свободного порта в диапазоне"""
        try:
            # Получаем список занятых портов из Docker
            used_ports = set()
            
            for container in self.docker_client.containers.list():
                ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
                for port_binding in ports.values():
                    if port_binding:
                        for binding in port_binding:
                            if binding.get('HostPort'):
                                used_ports.add(int(binding['HostPort']))
            
            # Ищем свободный порт
            for port in range(self.port_range_start, self.port_range_end + 1):
                if port not in used_ports:
                    # Дополнительная проверка через socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        sock.bind(('0.0.0.0', port))
                        sock.close()
                        logger.info(f"🔓 Найден свободный порт: {port}")
                        return port
                    except OSError:
                        continue
                    finally:
                        sock.close()
            
            logger.error("❌ Нет свободных портов в диапазоне")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска свободного порта: {e}")
            return None

    def _get_server_ip(self) -> str:
        """Получение IP адреса сервера"""
        try:
            # Пытаемся получить внешний IP
            response = requests.get('http://httpbin.org/ip', timeout=5)
            if response.status_code == 200:
                return response.json().get('origin', 'localhost')
        except:
            pass
        
        # Fallback на локальный IP
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            return ip
        except:
            return 'localhost'

    def _send_command_result(self, command_id: str, result: Dict[str, Any], task_type: str = 'unknown'):
        """Отправка результата выполнения команды"""
        try:
            result_data = {
                'task_id': command_id,
                'agent_id': self.agent_id,
                'task_type': task_type,
                'success': 'error' not in result,
                'result': result,
                'execution_time': 5.0  # время в секундах
            }
            
            # Используем тот же формат заголовков, что и для получения команд
            result_headers = {
                'Authorization': f'Bearer {self.agent_token}',
                'Content-Type': 'application/json',
                'X-Agent-ID': self.agent_id
            }
            
            logger.info(f"📤 Отправка результата команды {command_id}: {result_data}")
            
            response = requests.post(
                f"{self.server_url}/api2/appliku/vps/command-result",
                json=result_data,
                headers=result_headers,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Результат команды {command_id} отправлен успешно")
            else:
                logger.error(f"❌ Ошибка отправки результата: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки результата команды: {e}")

    def _deploy_git_repository(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Развертывание приложения из Git репозитория"""
        try:
            app_id = data.get('app_id')
            git_url = data.get('git_url')
            branch = data.get('branch', 'main')
            app_type = data.get('app_type', 'auto')
            
            logger.info(f"📥 Git развертывание приложения {app_id} из {git_url}")
            
            if not git_url:
                return {'error': 'Git URL не указан'}
            
            # Находим свободный порт
            external_port = self._find_free_port()
            if not external_port:
                return {'error': 'Нет свободных портов'}
            
            # Создаем директорию для приложения (очищаем если существует)
            app_dir = f"/opt/appliku/apps/{app_id}"
            if os.path.exists(app_dir):
                shutil.rmtree(app_dir)
            os.makedirs(app_dir)
            
            # Клонируем репозиторий
            logger.info(f"📥 Клонирование {git_url} (ветка: {branch})")
            clone_cmd = f"cd {app_dir} && git clone -b {branch} {git_url} ."
            result = subprocess.run(clone_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                return {'error': f'Ошибка клонирования: {result.stderr}'}
            
            # Определяем тип приложения если auto
            if app_type == 'auto':
                app_type = self._detect_app_type(app_dir)
            
            # Создаем requirements.txt для Python приложений если его нет
            if app_type == 'python' and not os.path.exists(os.path.join(app_dir, 'requirements.txt')):
                requirements_content = self._generate_requirements_txt()
                with open(os.path.join(app_dir, 'requirements.txt'), 'w') as f:
                    f.write(requirements_content)
                logger.info(f"📝 Создан requirements.txt для Python приложения")
            
            # Определяем главный файл для Python приложений
            main_file = self._find_main_file(app_dir, app_type)
            
            # Создаем Dockerfile если его нет
            dockerfile_path = os.path.join(app_dir, 'Dockerfile')
            if not os.path.exists(dockerfile_path):
                dockerfile_content = self._generate_dockerfile(app_type, external_port, main_file)
                with open(dockerfile_path, 'w') as f:
                    f.write(dockerfile_content)
                logger.info(f"📝 Создан Dockerfile для {app_type} с главным файлом {main_file}")
            
            # Собираем образ
            image_name = f"appliku-app-{app_id}"
            logger.info(f"🔨 Сборка образа {image_name}")
            
            image, logs = self.docker_client.images.build(
                path=app_dir,
                tag=image_name,
                rm=True
            )
            
            # Останавливаем существующий контейнер
            container_name = f"appliku-{app_id}"
            try:
                existing = self.docker_client.containers.get(container_name)
                existing.stop()
                existing.remove()
                logger.info(f"🔄 Остановлен существующий контейнер: {container_name}")
            except docker.errors.NotFound:
                pass
            
            # Получаем переменные окружения
            environment_vars = data.get('environment_vars', {})
            
            # Создаем .env файл если есть переменные окружения
            if environment_vars:
                env_file_path = os.path.join(app_dir, '.env')
                with open(env_file_path, 'w') as f:
                    for key, value in environment_vars.items():
                        f.write(f"{key}={value}\n")
                logger.info(f"📝 Создан .env файл с {len(environment_vars)} переменными")
            
            # Запускаем контейнер
            container = self.docker_client.containers.run(
                image_name,
                detach=True,
                name=container_name,
                ports={external_port: external_port},
                environment=environment_vars,  # Передаем переменные окружения
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
                return {'error': f'Контейнер не запустился. Статус: {container.status}'}
            
        except Exception as e:
            logger.error(f"❌ Ошибка Git развертывания: {e}")
            return {'error': str(e)}

    def _detect_app_type(self, app_dir: str) -> str:
        """Определение типа приложения"""
        if os.path.exists(os.path.join(app_dir, 'package.json')):
            return 'node'
        elif os.path.exists(os.path.join(app_dir, 'requirements.txt')):
            return 'python'
        elif os.path.exists(os.path.join(app_dir, 'composer.json')):
            return 'php'
        elif os.path.exists(os.path.join(app_dir, 'go.mod')):
            return 'go'
        elif os.path.exists(os.path.join(app_dir, 'main.py')) or os.path.exists(os.path.join(app_dir, 'app.py')):
            return 'python'
        else:
            return 'static'

    def _generate_dockerfile(self, app_type: str, port: int, main_file: str = None) -> str:
        """Генерация Dockerfile для разных типов приложений"""
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
# Поддержка переменных окружения
ENV PYTHONUNBUFFERED=1
CMD ["python", "{main_file or 'main.py'}"]''',
            'php': f'''FROM php:8.1-apache
COPY . /var/www/html/
EXPOSE 80''',
            'static': f'''FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE 80'''
        }
        
        return dockerfiles.get(app_type, dockerfiles['static'])

    def _find_main_file(self, app_dir: str, app_type: str) -> str:
        """Поиск главного файла приложения"""
        if app_type == 'python':
            # Ищем Python файлы в порядке приоритета
            main_files = ['main.py', 'app.py', 'bot.py', 'server.py', 'index.py']
            for file in main_files:
                if os.path.exists(os.path.join(app_dir, file)):
                    return file
            # Если ничего не найдено, возвращаем main.py по умолчанию
            return 'main.py'
        elif app_type == 'node':
            return 'index.js'
        else:
            return 'index.html'
    
    def _generate_requirements_txt(self) -> str:
        """Генерация базового requirements.txt для Python приложений"""
        return """flask==2.3.3
requests==2.31.0
python-dotenv==1.0.0
pyTelegramBotAPI==4.14.0
python-dotenv==1.0.0"""

    def _stop_application(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Остановка приложения"""
        try:
            app_id = data.get('app_id')
            logger.info(f"⏹️ Остановка приложения {app_id}")
            
            # Ищем контейнеры приложения
            containers = self.docker_client.containers.list(
                filters={'label': f'appliku.app_id={app_id}'}
            )
            
            if not containers:
                return {'error': f'No containers found for app {app_id}'}
            
            stopped_containers = []
            for container in containers:
                container.stop()
                stopped_containers.append(container.name)
                logger.info(f"⏹️ Остановлен контейнер: {container.name}")
            
            return {
                'success': True,
                'result': {
                    'stopped_containers': stopped_containers,
                    'status': 'stopped'
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки приложения: {e}")
            return {'error': str(e)}

    def _restart_application(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Перезапуск приложения"""
        try:
            app_id = data.get('app_id')
            logger.info(f"🔄 Перезапуск приложения {app_id}")
            
            # Ищем контейнеры приложения
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
                logger.info(f"🔄 Перезапущен контейнер: {container.name}")
            
            return {
                'success': True,
                'result': {
                    'restarted_containers': restarted_containers,
                    'status': 'running'
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка перезапуска приложения: {e}")
            return {'error': str(e)}

    def _delete_application(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Удаление приложения"""
        try:
            app_id = data.get('app_id')
            logger.info(f"🗑️ Удаление приложения {app_id}")
            
            # Ищем контейнеры приложения
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
                logger.info(f"🗑️ Удален контейнер: {container.name}")
            
            # Удаляем директорию приложения
            app_dir = f"/opt/appliku/apps/{app_id}"
            if os.path.exists(app_dir):
                shutil.rmtree(app_dir)
                logger.info(f"🗑️ Удалена директория: {app_dir}")
            
            return {
                'success': True,
                'result': {
                    'removed_containers': removed_containers,
                    'status': 'deleted'
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления приложения: {e}")
            return {'error': str(e)}

    def _get_container_logs(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Получение логов контейнера"""
        try:
            container_name = data.get('container_name')
            lines = data.get('lines', 100)
            
            logger.info(f"📋 Получение логов контейнера {container_name} (строк: {lines})")
            
            if not container_name:
                return {'error': 'Container name not specified'}
            
            # Ищем контейнер по имени
            try:
                container = self.docker_client.containers.get(container_name)
            except docker.errors.NotFound:
                return {'error': f'Container {container_name} not found'}
            
            # Получаем логи
            logs = container.logs(tail=lines, timestamps=True).decode('utf-8', errors='ignore')
            
            if not logs:
                logs = "Логи пусты или контейнер не запускался"
            
            return {
                'success': True,
                'result': {
                    'container_name': container_name,
                    'container_id': container.id,
                    'container_status': container.status,
                    'logs': logs,
                    'lines_count': len(logs.splitlines())
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения логов контейнера: {e}")
            return {'error': str(e)}

def main():
    """Главная функция"""
    # Получаем настройки из переменных окружения
    server_url = os.getenv('APPLIKU_SERVER_URL', 'http://31.169.124.43:8000')
    agent_token = os.getenv('APPLIKU_AGENT_TOKEN', 'test-agent-token-001')
    agent_id = os.getenv('APPLIKU_AGENT_ID', 'test-agent-001')
    
    logger.info(f"🚀 Запуск агента Appliku с Compose поддержкой")
    logger.info(f"🆔 Agent ID: {agent_id}")
    logger.info(f"🌐 Server: {server_url}")
    
    # Создаем и запускаем агент
    agent = ApplikuAgentCompose(server_url, agent_token, agent_id)
    
    # Обработка сигналов для корректного завершения
    def signal_handler(signum, frame):
        logger.info("🛑 Получен сигнал завершения")
        agent.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        agent.start()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка агента: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
