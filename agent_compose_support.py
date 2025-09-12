#!/usr/bin/env python3
"""
AppPilot Agent - Main Working Agent
Основной агент который подключается к серверу и выполняет задачи
"""

import os
import sys
import time
import yaml
import json
import logging
import signal
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import docker
import docker.errors
import subprocess

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Только вывод в консоль для Docker
    ]
)
logger = logging.getLogger(__name__)

class AppPilotAgent:
    """Основной рабочий AppPilot агент"""
    
    def __init__(self):
        self.config_file = Path("/opt/apppilot/config.yml")
        self.running = True
        self.config = {}
        self.session = requests.Session()
        self.docker_client = None
        
        # Сигналы для корректного завершения
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Загружаем конфигурацию
        self.load_config()
        
        # Инициализируем Docker клиент
        self.init_docker()
        
    def signal_handler(self, signum, frame):
        """Обработка сигналов завершения"""
        logger.info(f"Получен сигнал {signum}, завершаем работу...")
        self.running = False
        sys.exit(0)
    
    def load_config(self):
        """Загрузка конфигурации"""
        try:
            if not self.config_file.exists():
                logger.error("❌ Файл конфигурации не найден")
                sys.exit(1)
            
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f)
            
            # Проверяем обязательные поля
            required_fields = ['agent_id', 'central_server', 'agent_token', 'vps_id']
            for field in required_fields:
                if field not in self.config:
                    logger.error(f"❌ Отсутствует обязательное поле: {field}")
                    sys.exit(1)
            
            logger.info(f"✅ Конфигурация загружена: {self.config['agent_id']}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
            sys.exit(1)
    
    def init_docker(self):
        """Инициализация Docker клиента"""
        try:
            self.docker_client = docker.from_env()
            logger.info("✅ Docker клиент инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Docker: {e}")
            self.docker_client = None

    def find_free_port(self, start_port: int = 8001, end_port: int = 9000) -> int:
        """Поиск свободного порта в диапазоне"""
        try:
            import socket
            
            # Получаем список используемых портов из Docker
            used_ports = set()
            if self.docker_client:
                for container in self.docker_client.containers.list():
                    for port_binding in container.ports.values():
                        if port_binding:
                            for binding in port_binding:
                                if binding.get('HostPort'):
                                    used_ports.add(int(binding['HostPort']))
            
            # Ищем свободный порт
            for port in range(start_port, end_port + 1):
                if port not in used_ports:
                    # Дополнительная проверка через socket
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.bind(('localhost', port))
                            logger.info(f"✅ Найден свободный порт: {port}")
                            return port
                    except OSError:
                        continue
            
            logger.warning(f"⚠️ Не найден свободный порт в диапазоне {start_port}-{end_port}")
            return start_port
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска свободного порта: {e}")
            return start_port
    
    def register_with_server(self):
        """Регистрация агента на сервере"""
        try:
            url = f"{self.config['central_server']}/api2/appliku/vps/register-agent"
            
            data = {
                'agent_id': self.config['agent_id'],
                'agent_version': '1.0.0',
                'system_info': {
                    'vps_id': self.config['vps_id'],
                    'status': 'online',
                    'capabilities': ['docker', 'compose', 'deploy'],
                    'timestamp': datetime.now().isoformat()
                }
            }
            
            headers = {
                'Authorization': f'Bearer {self.config["agent_token"]}',
                'Content-Type': 'application/json'
            }
            
            response = self.session.post(url, json=data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                logger.info("✅ Агент зарегистрирован на сервере")
                return True
            else:
                logger.error(f"❌ Ошибка регистрации: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации: {e}")
            return False
    
    def get_tasks(self):
        """Получение задач от сервера"""
        try:
            url = f"{self.config['central_server']}/api2/appliku/vps/commands"
            
            headers = {
                'Authorization': f'Bearer {self.config["agent_token"]}',
                'Content-Type': 'application/json'
            }
            
            params = {'agent_id': self.config['agent_id']}
            response = self.session.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                tasks = response.json()
                # API возвращает список задач напрямую
                if isinstance(tasks, list):
                    return tasks
                # Или объект с полем tasks
                elif isinstance(tasks, dict) and 'tasks' in tasks:
                    return tasks['tasks']
                else:
                    logger.warning(f"⚠️ Неожиданный формат ответа: {type(tasks)}")
                    return []
            else:
                logger.error(f"❌ Ошибка получения задач: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения задач: {e}")
            return []
    
    def submit_task_result(self, task_id: str, result: Dict[str, Any], task: Dict[str, Any]):
        """Отправка результата выполнения задачи"""
        try:
            url = f"{self.config['central_server']}/api2/appliku/vps/command-result"
            
            data = {
                'task_id': task_id,
                'agent_id': self.config['agent_id'],
                'task_type': task.get('task_type', 'unknown'),
                'success': result.get('success', False),
                'result': result.get('result', {}),
                'error': result.get('error', ''),
                'execution_time': result.get('execution_time', 0)
            }
            
            headers = {
                'Authorization': f'Bearer {self.config["agent_token"]}',
                'Content-Type': 'application/json'
            }
            
            response = self.session.post(url, json=data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                logger.info(f"✅ Результат задачи {task_id} отправлен")
                return True
            else:
                logger.error(f"❌ Ошибка отправки результата: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки результата: {e}")
            return False
    
    def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Выполнение задачи"""
        try:
            task_type = task.get('task_type')
            task_data = task.get('data', {})
            
            logger.info(f"🚀 Выполняем задачу: {task_type}")
            
            start_time = time.time()
            
            if task_type == 'deploy_compose':
                result = self.deploy_compose_app(task_data)
            elif task_type == 'deploy_git':
                result = self.deploy_git_app(task_data)
            elif task_type == 'update_application':
                result = self.update_application(task_data)
            elif task_type == 'start_container':
                result = self.start_container(task_data)
            elif task_type == 'stop_container':
                result = self.stop_container(task_data)
            elif task_type == 'delete_container':
                result = self.delete_container(task_data)
            elif task_type == 'scan_containers':
                result = self.scan_containers()
            else:
                result = {'success': False, 'error': f'Неизвестный тип задачи: {task_type}'}
            
            execution_time = time.time() - start_time
            
            return {
                'success': result.get('success', False),
                'result': result.get('result', {}),
                'error': result.get('error', ''),
                'execution_time': execution_time
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения задачи: {e}")
            return {
                'success': False,
                'error': str(e),
                'execution_time': 0
            }
    
    def deploy_compose_app(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Развертывание Docker Compose приложения"""
        try:
            app_name = task_data.get('app_name')
            compose_file = task_data.get('compose_file')
            app_id = task_data.get('app_id')
            
            logger.info(f"🚀 Развертываем приложение: {app_name}")
            
            # Создаем директорию для приложения
            app_dir = Path(f"/opt/apppilot/apps/{app_id}")
            app_dir.mkdir(parents=True, exist_ok=True)
            
            # Сохраняем docker-compose.yml
            compose_path = app_dir / "docker-compose.yml"
            with open(compose_path, 'w') as f:
                f.write(compose_file)
            
            # Добавляем лейблы для docker-compose
            compose_labels = {
                'appliku.app_id': app_id,
                'appliku.type': 'compose',
                'appliku.created_by': 'apppilot-agent',
                'appliku.vps_id': self.config['vps_id'],
                'appliku.deployment_time': datetime.now().isoformat()
            }
            
            # Создаем .env файл с лейблами для docker-compose
            env_file = app_dir / ".env"
            with open(env_file, 'w') as f:
                for key, value in compose_labels.items():
                    f.write(f"{key}={value}\n")
            
            # Запускаем docker-compose
            result = subprocess.run(
                ['docker', 'compose', '-f', str(compose_path), 'up', '-d'],
                capture_output=True,
                text=True,
                cwd=app_dir
            )
            
            if result.returncode == 0:
                logger.info(f"✅ Приложение {app_name} развернуто успешно")
                return {
                    'success': True,
                    'result': {
                        'app_id': app_id,
                        'app_name': app_name,
                        'status': 'deployed',
                        'compose_file': str(compose_path)
                    }
                }
            else:
                logger.error(f"❌ Ошибка развертывания: {result.stderr}")
                return {
                    'success': False,
                    'error': result.stderr
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка развертывания: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def deploy_git_app(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Развертывание приложения из Git репозитория"""
        try:
            logger.info(f"📋 Полученные данные задачи: {task_data}")
            app_id = task_data.get('app_id')
            git_url = task_data.get('git_url')
            branch = task_data.get('branch', 'main')
            app_type = task_data.get('app_type', 'auto')
            port = task_data.get('port', 8000)
            environment_vars = task_data.get('environment_vars', {})
            
            logger.info(f"🚀 Развертываем приложение из Git: {app_id}")
            logger.info(f"📦 Git URL: {git_url}, ветка: {branch}")
            
            # Если порт не указан, ищем свободный
            if port == 8000:
                port = self.find_free_port()
                logger.info(f"🔍 Автоматически назначен порт: {port}")
            
            # Создаем директорию для приложения
            app_dir = Path(f"/opt/apppilot/apps/{app_id}")
            if app_dir.exists():
                # Удаляем старую директорию если существует
                import shutil
                shutil.rmtree(app_dir)
            app_dir.mkdir(parents=True, exist_ok=True)
            
            # Клонируем Git репозиторий
            logger.info("📥 Клонируем Git репозиторий...")
            clone_result = subprocess.run(
                ['git', 'clone', '-b', branch, git_url, str(app_dir)],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if clone_result.returncode != 0:
                logger.error(f"❌ Ошибка клонирования Git: {clone_result.stderr}")
                return {
                    'success': False,
                    'error': f"Git clone failed: {clone_result.stderr}"
                }
            
            logger.info("✅ Git репозиторий клонирован")
            
            # Проверяем наличие Dockerfile
            dockerfile_path = app_dir / "Dockerfile"
            if not dockerfile_path.exists():
                logger.info("🔧 Dockerfile не найден, генерируем автоматически...")
                self._generate_dockerfile(app_dir, app_type, port)
            
            # Собираем Docker образ
            logger.info("🏗️ Собираем Docker образ...")
            # Очищаем app_id от недопустимых символов для Docker тегов
            safe_app_id = self._sanitize_app_id(app_id)
            image_name = f"apppilot-{safe_app_id}"
            build_result = subprocess.run(
                ['docker', 'build', '-t', image_name, '.'],
                capture_output=True,
                text=True,
                cwd=app_dir,
                timeout=600
            )
            
            if build_result.returncode != 0:
                logger.error(f"❌ Ошибка сборки Docker: {build_result.stderr}")
                return {
                    'success': False,
                    'error': f"Docker build failed: {build_result.stderr}"
                }
            
            logger.info("✅ Docker образ собран")
            
            # Останавливаем старый контейнер если существует
            container_name = f"apppilot-{safe_app_id}"
            try:
                old_container = self.docker_client.containers.get(container_name)
                logger.info(f"🛑 Останавливаем старый контейнер: {container_name}")
                old_container.stop()
                old_container.remove()
            except:
                pass
            
            # Запускаем новый контейнер
            logger.info(f"🚀 Запускаем контейнер на порту {port}...")
            
            # Подготавливаем переменные окружения
            env_vars = {
                'NODE_ENV': 'production',
                'PORT': str(port)
            }
            env_vars.update(environment_vars)
            
            # Добавляем лейблы для идентификации контейнера AppPilot
            labels = {
                'appliku.app_id': app_id,
                'appliku.type': 'git',
                'appliku.created_by': 'apppilot-agent',
                'appliku.vps_id': self.config['vps_id'],
                'appliku.deployment_time': datetime.now().isoformat(),
                'appliku.git_url': git_url,
                'appliku.branch': branch,
                'appliku.port': str(port)
            }
            
            container = self.docker_client.containers.run(
                image_name,
                name=container_name,
                ports={f'{port}/tcp': port},
                environment=env_vars,
                restart_policy={'Name': 'unless-stopped'},
                labels=labels,
                detach=True
            )
            
            logger.info(f"✅ Контейнер запущен: {container.id}")
            
            # Формируем app_url
            app_url = f"http://185.135.82.248:{port}"
            
            return {
                'success': True,
                'result': {
                    'app_type': 'git',
                    'container_id': container.id,
                    'container_name': container_name,
                    'external_port': port,
                    'app_url': app_url,
                    'git_url': git_url,
                    'branch': branch,
                    'app_type_detected': app_type,
                    'status': 'running'
                }
            }
                
        except Exception as e:
            logger.error(f"❌ Ошибка развертывания из Git: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def update_application(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновление приложения из Git репозитория"""
        try:
            app_id = task_data.get('app_id')
            git_url = task_data.get('git_url')
            branch = task_data.get('branch', 'main')
            
            logger.info(f"🔄 Обновляем приложение: {app_id}")
            logger.info(f"📦 Git URL: {git_url}, ветка: {branch}")
            
            # Создаем директорию для приложения
            app_dir = Path(f"/opt/apppilot/apps/{app_id}")
            if not app_dir.exists():
                return {
                    'success': False,
                    'error': f"Приложение {app_id} не найдено"
                }
            
            # Переходим в директорию приложения
            os.chdir(app_dir)
            
            # Получаем последние изменения
            logger.info("📥 Получаем последние изменения из Git...")
            fetch_result = subprocess.run(
                ['git', 'fetch', 'origin'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if fetch_result.returncode != 0:
                logger.error(f"❌ Ошибка fetch: {fetch_result.stderr}")
                return {
                    'success': False,
                    'error': f"Git fetch failed: {fetch_result.stderr}"
                }
            
            # Переключаемся на нужную ветку
            checkout_result = subprocess.run(
                ['git', 'checkout', branch],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if checkout_result.returncode != 0:
                logger.error(f"❌ Ошибка checkout: {checkout_result.stderr}")
                return {
                    'success': False,
                    'error': f"Git checkout failed: {checkout_result.stderr}"
                }
            
            # Сбрасываем к последнему коммиту
            reset_result = subprocess.run(
                ['git', 'reset', '--hard', f'origin/{branch}'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if reset_result.returncode != 0:
                logger.error(f"❌ Ошибка reset: {reset_result.stderr}")
                return {
                    'success': False,
                    'error': f"Git reset failed: {reset_result.stderr}"
                }
            
            logger.info("✅ Код обновлен из Git")
            
            # Пересобираем Docker образ
            logger.info("🏗️ Пересобираем Docker образ...")
            # Очищаем app_id от недопустимых символов для Docker тегов
            safe_app_id = self._sanitize_app_id(app_id)
            image_name = f"apppilot-{safe_app_id}"
            build_result = subprocess.run(
                ['docker', 'build', '-t', image_name, '.'],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if build_result.returncode != 0:
                logger.error(f"❌ Ошибка сборки Docker: {build_result.stderr}")
                return {
                    'success': False,
                    'error': f"Docker build failed: {build_result.stderr}"
                }
            
            logger.info("✅ Docker образ пересобран")
            
            # Перезапускаем контейнер
            container_name = f"apppilot-{safe_app_id}"
            try:
                container = self.docker_client.containers.get(container_name)
                logger.info(f"🔄 Перезапускаем контейнер: {container_name}")
                
                # Обновляем лейблы с новым временем обновления
                container.labels.update({
                    'appliku.last_updated': datetime.now().isoformat(),
                    'appliku.update_count': str(int(container.labels.get('appliku.update_count', '0')) + 1)
                })
                
                container.restart()
            except:
                logger.error(f"❌ Контейнер {container_name} не найден")
                return {
                    'success': False,
                    'error': f"Container {container_name} not found"
                }
            
            logger.info(f"✅ Приложение {app_id} обновлено и перезапущено")
            
            return {
                'success': True,
                'result': {
                    'app_id': app_id,
                    'container_id': container.id,
                    'status': 'updated',
                    'git_url': git_url,
                    'branch': branch
                }
            }
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления приложения: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _sanitize_app_id(self, app_id: str) -> str:
        """Очищает app_id от недопустимых символов для Docker тегов"""
        import re
        # Убираем кириллические символы и другие недопустимые символы
        # Docker теги могут содержать только: [a-zA-Z0-9][a-zA-Z0-9_.-]
        sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '', app_id)
        # Убираем точки в начале и конце
        sanitized = sanitized.strip('.')
        # Если после очистки строка пустая, используем fallback
        if not sanitized:
            sanitized = "app"
        # Ограничиваем длину
        if len(sanitized) > 50:
            sanitized = sanitized[:50]
        logger.info(f"🔧 Очищен app_id: '{app_id}' → '{sanitized}'")
        return sanitized

    def _generate_dockerfile(self, app_dir: Path, app_type: str, port: int = 8000):
        """Автоматическая генерация Dockerfile"""
        try:
            dockerfile_content = ""
            
            if app_type == 'nodejs':
                dockerfile_content = f"""FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE {port}
CMD ["npm", "start"]
"""
            elif app_type == 'python':
                # Определяем главный файл приложения
                main_file = self._find_python_main_file(app_dir)
                
                # Проверяем наличие requirements.txt
                if (app_dir / "requirements.txt").exists():
                    dockerfile_content = f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE {port}
# Поддержка переменных окружения
ENV PYTHONUNBUFFERED=1
ENV PORT={port}
CMD ["python", "{main_file}"]
"""
                else:
                    # Если requirements.txt нет, создаем базовый и используем его
                    logger.info("📦 requirements.txt не найден, создаем базовый...")
                    self._generate_requirements_txt(app_dir)
                    dockerfile_content = f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE {port}
# Поддержка переменных окружения
ENV PYTHONUNBUFFERED=1
ENV PORT={port}
CMD ["python", "{main_file}"]
"""
            elif app_type == 'php':
                dockerfile_content = f"""FROM php:8.1-apache
WORKDIR /var/www/html
COPY . .
EXPOSE {port}
CMD ["apache2-foreground"]
"""
            else:
                # Автоопределение типа приложения
                if (app_dir / "package.json").exists():
                    dockerfile_content = f"""FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE {port}
CMD ["npm", "start"]
"""
                elif (app_dir / "requirements.txt").exists():
                    dockerfile_content = f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE {port}
# Поддержка переменных окружения
ENV PYTHONUNBUFFERED=1
ENV PORT={port}
CMD ["python", "app.py"]
"""
                else:
                    dockerfile_content = f"""FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE {port}
CMD ["nginx", "-g", "daemon off;"]
"""
            
            # Записываем Dockerfile
            dockerfile_path = app_dir / "Dockerfile"
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            
            logger.info(f"✅ Dockerfile сгенерирован для типа: {app_type} на порту {port}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации Dockerfile: {e}")
            raise
    
    def _find_python_main_file(self, app_dir: Path) -> str:
        """Находит главный файл Python приложения"""
        try:
            # Список возможных главных файлов в порядке приоритета
            possible_main_files = [
                'main.py',
                'app.py', 
                'bot.py',
                'server.py',
                'index.py',
                'run.py',
                'start.py'
            ]
            
            # Ищем существующие файлы
            for filename in possible_main_files:
                if (app_dir / filename).exists():
                    logger.info(f"🔍 Найден главный файл: {filename}")
                    return filename
            
            # Если не нашли стандартные файлы, ищем любой .py файл
            py_files = list(app_dir.glob("*.py"))
            if py_files:
                main_file = py_files[0].name
                logger.info(f"🔍 Используем первый найденный Python файл: {main_file}")
                return main_file
            
            # Если ничего не нашли, создаем простой Python файл
            logger.warning("⚠️ Главный Python файл не найден, создаем простой app.py")
            self._create_simple_python_app(app_dir)
            return "app.py"
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска главного Python файла: {e}")
            # Создаем простой Python файл в случае ошибки
            self._create_simple_python_app(app_dir)
            return "app.py"
    
    def _create_simple_python_app(self, app_dir: Path):
        """Создает простой Python файл если его нет"""
        try:
            app_content = '''#!/usr/bin/env python3
"""
Простое Python приложение для AppPilot
"""
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = f"""
        <html>
        <head><title>AppPilot Python App</title></head>
        <body>
            <h1>🚀 Python приложение успешно запущено!</h1>
            <p>Это автоматически сгенерированное приложение от AppPilot</p>
            <p>Время: {__import__('datetime').datetime.now()}</p>
            <p>Порт: {os.environ.get('PORT', '8000')}</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        # Отключаем логирование запросов
        pass

def main():
    port = int(os.environ.get('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"🚀 Сервер запущен на порту {port}")
    server.serve_forever()

if __name__ == "__main__":
    main()
'''
            
            app_file = app_dir / "app.py"
            with open(app_file, 'w') as f:
                f.write(app_content)
            
            logger.info("✅ Создан простой Python файл app.py")
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания Python файла: {e}")
    
    def start_container(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Запуск контейнера"""
        try:
            container_name = task_data.get('container_name')
            
            if not self.docker_client:
                return {'success': False, 'error': 'Docker клиент не инициализирован'}
            
            container = self.docker_client.containers.get(container_name)
            container.start()
            
            logger.info(f"✅ Контейнер {container_name} запущен")
            return {'success': True, 'result': {'status': 'started'}}
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска контейнера: {e}")
            return {'success': False, 'error': str(e)}
    
    def stop_container(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Остановка контейнера"""
        try:
            container_name = task_data.get('container_name')
            
            if not self.docker_client:
                return {'success': False, 'error': 'Docker клиент не инициализирован'}
            
            container = self.docker_client.containers.get(container_name)
            container.stop()
            
            logger.info(f"✅ Контейнер {container_name} остановлен")
            return {'success': True, 'result': {'status': 'stopped'}}
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки контейнера: {e}")
            return {'success': False, 'error': str(e)}
    
    def delete_container(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Удаление контейнера"""
        try:
            container_name = task_data.get('container_name')
            
            if not self.docker_client:
                return {'success': False, 'error': 'Docker клиент не инициализирован'}
            
            container = self.docker_client.containers.get(container_name)
            container.remove(force=True)
            
            logger.info(f"✅ Контейнер {container_name} удален")
            return {'success': True, 'result': {'status': 'deleted'}}
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления контейнера: {e}")
            return {'success': False, 'error': str(e)}
    
    def _generate_requirements_txt(self, app_dir: Path):
        """Генерация базового requirements.txt для Python приложений если его нет"""
        try:
            requirements_content = """flask==2.3.3
requests==2.31.0
python-dotenv==1.0.0
pyTelegramBotAPI==4.14.0
"""
            
            requirements_file = app_dir / "requirements.txt"
            with open(requirements_file, 'w') as f:
                f.write(requirements_content)
            
            logger.info("✅ Создан базовый requirements.txt")
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания requirements.txt: {e}")
    
    def get_real_container_status(self, app_id: str) -> str:
        """Получение реального статуса контейнера из Docker"""
        try:
            if not self.docker_client:
                logger.warning("⚠️ Docker клиент не инициализирован")
                return 'unknown'
            
            # Очищаем app_id от недопустимых символов для Docker тегов
            safe_app_id = self._sanitize_app_id(app_id)
            container_name = f"apppilot-{safe_app_id}"
            container = self.docker_client.containers.get(container_name)
            
            # Получаем реальный статус из Docker
            real_status = container.status
            
            # Маппинг Docker статусов на AppPilot статусы
            status_mapping = {
                'running': 'running',
                'exited': 'stopped', 
                'created': 'created',
                'restarting': 'restarting',
                'paused': 'paused',
                'dead': 'failed'
            }
            
            mapped_status = status_mapping.get(real_status, 'unknown')
            logger.debug(f"🔍 Контейнер {app_id}: Docker статус '{real_status}' → AppPilot статус '{mapped_status}'")
            
            return mapped_status
            
        except docker.errors.NotFound:
            logger.debug(f"🔍 Контейнер {app_id} не найден в Docker")
            return 'not_found'  # Контейнер не существует
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса контейнера {app_id}: {e}")
            return 'error'
    
    def get_applications_from_api(self) -> list:
        """Получение списка приложений из API сервера"""
        try:
            url = f"{self.config['central_server']}/api2/appliku/vps/{self.config['vps_id']}/applications"
            
            headers = {
                'Authorization': f'Bearer {self.config["agent_token"]}',
                'Content-Type': 'application/json'
            }
            
            response = self.session.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"🔍 Получен ответ от API: {type(data)}")
                
                # API может возвращать список напрямую или объект с полем applications
                if isinstance(data, list):
                    applications = data
                elif isinstance(data, dict) and 'applications' in data:
                    applications = data['applications']
                else:
                    logger.warning(f"⚠️ Неожиданный формат ответа: {data}")
                    return []
                
                logger.debug(f"🔍 Получено {len(applications)} приложений из API")
                return applications
            else:
                logger.error(f"❌ Ошибка получения приложений: {response.status_code}")
                logger.error(f"📝 Ответ: {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения приложений из API: {e}")
            return []
    
    def update_application_status(self, app_id: str, new_status: str):
        """Обновление статуса приложения в API сервере"""
        try:
            # Пока просто логируем различия - это поможет понять проблему
            logger.info(f"🔄 НАЙДЕНО РАЗЛИЧИЕ: {app_id} - текущий статус в API: 'deploying', реальный статус в Docker: '{new_status}'")
            logger.info(f"💡 Для исправления нужно обновить приложение {app_id} в базе данных")
            return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса приложения {app_id}: {e}")
            return False
    
    def get_all_appliku_containers(self):
        """Получает все контейнеры, созданные AppPilot"""
        try:
            containers = []
            
            for container in self.docker_client.containers.list(all=True):
                # Проверяем лейблы или имена для идентификации AppPilot контейнеров
                if (container.name.startswith('apppilot-') or 
                    container.labels.get('appliku.created_by') == 'apppilot-agent'):
                    
                    # Получаем детальную информацию о контейнере
                    container_info = {
                        'container_id': container.id,
                        'name': container.name,
                        'status': container.status,
                        'image': container.image.tags[0] if container.image.tags else 'unknown',
                        'created': container.attrs['Created'],
                        'ports': container.ports,
                        'labels': container.labels,
                        'app_id': container.labels.get('appliku.app_id'),
                        'app_type': container.labels.get('appliku.type'),
                        'vps_id': container.labels.get('appliku.vps_id'),
                        'git_url': container.labels.get('appliku.git_url'),
                        'branch': container.labels.get('appliku.branch'),
                        'port': container.labels.get('appliku.port'),
                        'deployment_time': container.labels.get('appliku.deployment_time')
                    }
                    
                    containers.append(container_info)
            
            logger.info(f"🔍 Найдено {len(containers)} контейнеров AppPilot")
            return containers
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения контейнеров AppPilot: {e}")
            return []
    
    def sync_all_applications_status(self):
        """Синхронизация статусов всех приложений с Docker"""
        try:
            logger.info("🔄 Начинаю синхронизацию статусов приложений...")
            
            # Получаем все приложения из API
            applications = self.get_applications_from_api()
            
            if not applications:
                logger.info("ℹ️ Нет приложений для синхронизации")
                return
            
            updated_count = 0
            
            for app in applications:
                app_id = app.get('app_id')
                if not app_id:
                    continue
                    
                current_status = app.get('status', 'unknown')
                real_status = self.get_real_container_status(app_id)
                
                # Если статус изменился, обновляем в API
                if real_status != current_status and real_status != 'error':
                    logger.info(f"🔄 Статус {app_id} изменился: {current_status} → {real_status}")
                    
                    if self.update_application_status(app_id, real_status):
                        updated_count += 1
                    else:
                        logger.warning(f"⚠️ Не удалось обновить статус {app_id}")
            
            if updated_count > 0:
                logger.info(f"✅ Синхронизация завершена: обновлено {updated_count} приложений")
            else:
                logger.info("ℹ️ Синхронизация завершена: изменений не найдено")
                
        except Exception as e:
            logger.error(f"❌ Ошибка синхронизации статусов: {e}")
    
    def scan_containers(self):
        """Сканирует все контейнеры и возвращает информацию о них"""
        try:
            logger.info("🔍 Начинаю сканирование всех контейнеров")
            logger.info("🔍 DEBUG: Метод scan_containers вызван")
            
            containers = []
            
            # Получаем все контейнеры (включая остановленные)
            all_containers = self.docker_client.containers.list(all=True)
            
            for container in all_containers:
                try:
                    # Определяем тип контейнера по лейблам и имени
                    container_type = "unknown"
                    app_id = None
                    
                    # Проверяем лейблы AppPilot
                    if container.labels.get('appliku.created_by') == 'apppilot-agent':
                        container_type = "apppilot"
                        app_id = container.labels.get('appliku.app_id')
                    elif container.name.startswith('apppilot-'):
                        container_type = "apppilot"
                        app_id = container.name.replace('apppilot-', '')
                    elif container.name in ['appliku-agent', 'agent-appliku-agent']:
                        container_type = "system"
                    elif container.name.startswith('python_api_server-'):
                        container_type = "system"
                    elif container.name.startswith('postgres-') or container.name.startswith('redis-'):
                        container_type = "system"
                    elif container.name.startswith('nginx-'):
                        container_type = "system"
                    else:
                        container_type = "other"
                    
                    # Получаем информацию о портах
                    ports_info = {}
                    if container.attrs.get('NetworkSettings', {}).get('Ports'):
                        for port_binding in container.attrs['NetworkSettings']['Ports'].values():
                            if port_binding:
                                for binding in port_binding:
                                    host_port = binding.get('HostPort')
                                    container_port = binding.get('ContainerPort')
                                    if host_port and container_port:
                                        ports_info[f"{host_port}->{container_port}"] = f"http://185.135.82.248:{host_port}"
                    
                    container_info = {
                        'container_id': container.id,
                        'name': container.name,
                        'status': container.status,
                        'image': container.image.tags[0] if container.image.tags else 'unknown',
                        'created': container.attrs['Created'],
                        'ports': ports_info,
                        'labels': container.labels,
                        'container_type': container_type,
                        'app_id': app_id,
                        'app_url': list(ports_info.values())[0] if ports_info else None
                    }
                    
                    containers.append(container_info)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка получения информации о контейнере {container.name}: {e}")
                    continue
            
            logger.info(f"✅ Сканирование завершено: найдено {len(containers)} контейнеров")
            
            result_data = {
                'success': True,
                'result': {
                    'containers': containers,
                    'total_count': len(containers),
                    'apppilot_count': len([c for c in containers if c['container_type'] == 'apppilot']),
                    'system_count': len([c for c in containers if c['container_type'] == 'system']),
                    'other_count': len([c for c in containers if c['container_type'] == 'other'])
                }
            }
            
            logger.info(f"🔍 DEBUG: Возвращаем результат: {result_data}")
            return result_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка сканирования контейнеров: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def run(self):
        """Основной цикл работы агента"""
        try:
            logger.info("🚀 AppPilot Agent запущен")
            
            # Регистрируемся на сервере
            if not self.register_with_server():
                logger.error("❌ Не удалось зарегистрироваться на сервере")
                return False
            
            logger.info("✅ Агент зарегистрирован, начинаем работу...")
            
            # Основной цикл обработки задач
            last_sync_time = time.time()
            sync_interval = 180  # 3 минуты
            
            while self.running:
                try:
                    current_time = time.time()
                    
                    # Получаем задачи
                    tasks = self.get_tasks()
                    
                    for task in tasks:
                        if not self.running:
                            break
                        
                        task_id = task.get('id')
                        task_status = task.get('status')
                        
                        if not task_id:
                            continue
                        
                        # Выполняем только задачи со статусом 'pending'
                        if task_status != 'pending':
                            logger.info(f"⏭️ Пропускаем задачу {task_id} со статусом '{task_status}'")
                            continue
                        
                        # Выполняем задачу
                        result = self.execute_task(task)
                        
                        # Отправляем результат
                        self.submit_task_result(task_id, result, task)
                    
                    # Синхронизируем статусы каждые 3 минуты
                    if current_time - last_sync_time >= sync_interval:
                        logger.info("⏰ Время синхронизации статусов приложений")
                        self.sync_all_applications_status()
                        last_sync_time = current_time
                    
                    # Ждем перед следующей проверкой
                    time.sleep(30)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка в основном цикле: {e}")
                    time.sleep(60)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            return False

def main():
    """Главная функция"""
    agent = AppPilotAgent()
    
    try:
        success = agent.run()
        if success:
            logger.info("✅ AppPilot Agent успешно завершил работу")
            sys.exit(0)
        else:
            logger.error("❌ AppPilot Agent завершился с ошибкой")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("🛑 Работа прервана пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
