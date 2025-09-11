#!/usr/bin/env python3
"""
AppPilot Agent - Wait for Configuration Mode
Агент работает в режиме ожидания конфигурации после установки
"""

import os
import sys
import time
import yaml
import json
import logging
import signal
import threading
from pathlib import Path
from typing import Dict, Any, Optional
import subprocess
import requests
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/apppilot-agent-wait.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AppPilotAgentWait:
    """Агент AppPilot в режиме ожидания конфигурации"""
    
    def __init__(self):
        self.config_file = Path("/opt/apppilot-agent/config.yml")
        self.agent_dir = Path("/opt/apppilot-agent")
        self.running = True
        self.config = {}
        self.config_loaded = False
        
        # Сигналы для корректного завершения
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # HTTP сервер для получения конфигурации
        self.http_server = None
        
    def signal_handler(self, signum, frame):
        """Обработка сигналов завершения"""
        logger.info(f"Получен сигнал {signum}, завершаем работу...")
        self.running = False
        if self.http_server:
            self.http_server.shutdown()
        sys.exit(0)
    
    def start_config_server(self):
        """Запуск HTTP сервера для получения конфигурации"""
        try:
            from http.server import HTTPServer, BaseHTTPRequestHandler
            import socketserver
            
            class ConfigHandler(BaseHTTPRequestHandler):
                def __init__(self, *args, agent_instance=None, **kwargs):
                    self.agent = agent_instance
                    super().__init__(*args, **kwargs)
                
                def do_POST(self):
                    """Получение конфигурации"""
                    if self.path == '/config':
                        content_length = int(self.headers['Content-Length'])
                        post_data = self.rfile.read(content_length)
                        
                        try:
                            config = json.loads(post_data.decode('utf-8'))
                            logger.info(f"Получена конфигурация: {config}")
                            
                            # Сохраняем конфигурацию
                            if self.agent.save_config(config):
                                self.send_response(200)
                                self.send_header('Content-type', 'application/json')
                                self.end_headers()
                                response = {'status': 'success', 'message': 'Configuration saved'}
                                self.wfile.write(json.dumps(response).encode())
                            else:
                                self.send_response(500)
                                self.send_header('Content-type', 'application/json')
                                self.end_headers()
                                response = {'status': 'error', 'message': 'Failed to save configuration'}
                                self.wfile.write(json.dumps(response).encode())
                                
                        except Exception as e:
                            logger.error(f"Ошибка обработки конфигурации: {e}")
                            self.send_response(400)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            response = {'status': 'error', 'message': str(e)}
                            self.wfile.write(json.dumps(response).encode())
                    else:
                        self.send_response(404)
                        self.end_headers()
                
                def do_GET(self):
                    """Статус агента"""
                    if self.path == '/status':
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        
                        status = {
                            'status': 'waiting_for_config' if not self.agent.config_loaded else 'configured',
                            'timestamp': datetime.now().isoformat(),
                            'config_loaded': self.agent.config_loaded
                        }
                        self.wfile.write(json.dumps(status).encode())
                    else:
                        self.send_response(404)
                        self.end_headers()
                
                def log_message(self, format, *args):
                    """Отключение стандартного логирования HTTP сервера"""
                    pass
            
            # Создаем сервер
            handler = type('ConfigHandler', (ConfigHandler,), {'agent_instance': self})
            self.http_server = HTTPServer(('0.0.0.0', 8000), handler)
            
            logger.info("🚀 HTTP сервер запущен на порту 8000")
            logger.info("⏳ Ожидаем загрузку конфигурации...")
            
            # Запускаем сервер в отдельном потоке
            server_thread = threading.Thread(target=self.http_server.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска HTTP сервера: {e}")
            return False
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """Сохранение конфигурации"""
        try:
            # Проверяем обязательные поля
            required_fields = ['agent_id', 'central_server', 'agent_token', 'vps_id']
            for field in required_fields:
                if field not in config:
                    logger.error(f"Отсутствует обязательное поле: {field}")
                    return False
            
            # Сохраняем конфигурацию
            with open(self.config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            
            self.config = config
            self.config_loaded = True
            
            logger.info(f"✅ Конфигурация сохранена: {config['agent_id']}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации: {e}")
            return False
    
    def wait_for_config(self):
        """Ожидание загрузки конфигурации"""
        logger.info("⏳ Ожидаем загрузку конфигурации...")
        
        while self.running and not self.config_loaded:
            try:
                # Проверяем файл конфигурации
                if self.config_file.exists():
                    with open(self.config_file, 'r') as f:
                        config = yaml.safe_load(f)
                    
                    # Проверяем что все параметры загружены
                    if config and all([
                        config.get('agent_id') != 'PLACEHOLDER',
                        config.get('central_server') != 'PLACEHOLDER',
                        config.get('agent_token') != 'PLACEHOLDER',
                        config.get('vps_id') != 'PLACEHOLDER'
                    ]):
                        self.config = config
                        self.config_loaded = True
                        logger.info(f"✅ Конфигурация загружена из файла: {config['agent_id']}")
                        break
                
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"Ошибка проверки конфигурации: {e}")
                time.sleep(10)
    
    def start_main_agent(self):
        """Запуск основного агента с загруженной конфигурацией"""
        try:
            logger.info("🚀 Запускаем основной AppPilot Agent...")
            
            # Проверяем что основной агент установлен
            main_agent_script = self.agent_dir / "agent_compose_support.py"
            if not main_agent_script.exists():
                logger.error("❌ Основной агент не найден")
                return False
            
            # Запускаем основной агент
            env = os.environ.copy()
            env.update({
                'AGENT_ID': self.config['agent_id'],
                'CENTRAL_SERVER': self.config['central_server'],
                'AGENT_TOKEN': self.config['agent_token'],
                'VPS_ID': str(self.config['vps_id'])
            })
            
            # Запускаем основной агент
            process = subprocess.Popen([
                sys.executable, str(main_agent_script)
            ], env=env, cwd=str(self.agent_dir))
            
            logger.info(f"✅ Основной агент запущен (PID: {process.pid})")
            
            # Ждем завершения
            process.wait()
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска основного агента: {e}")
            return False
    
    def run(self):
        """Основной цикл работы"""
        try:
            logger.info("🚀 AppPilot Agent Wait Mode запущен")
            
            # Запускаем HTTP сервер для получения конфигурации
            if not self.start_config_server():
                logger.error("❌ Не удалось запустить HTTP сервер")
                return False
            
            # Ожидаем загрузку конфигурации
            self.wait_for_config()
            
            if not self.config_loaded:
                logger.error("❌ Конфигурация не загружена")
                return False
            
            # Останавливаем HTTP сервер
            if self.http_server:
                self.http_server.shutdown()
                logger.info("🛑 HTTP сервер остановлен")
            
            # Запускаем основной агент
            return self.start_main_agent()
            
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            return False

def main():
    """Главная функция"""
    agent = AppPilotAgentWait()
    
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
