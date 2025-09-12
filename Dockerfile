FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    git \
    docker.io \
    docker-compose \
    && rm -rf /var/lib/apt/lists/*

# Создание пользователя apppilot
RUN useradd -m -s /bin/bash apppilot && \
    usermod -aG docker apppilot

# Создание директорий
RUN mkdir -p /opt/apppilot /opt/apppilot/apps /var/log

# Копирование файлов агента
COPY agent_compose_support.py /opt/apppilot/agent.py
COPY requirements.txt /opt/apppilot/

# Установка Python зависимостей
RUN pip install --no-cache-dir -r /opt/apppilot/requirements.txt

# Установка прав
RUN chown -R apppilot:apppilot /opt/apppilot /var/log

# Рабочая директория
WORKDIR /opt/apppilot

# Создание конфигурационного файла (будет перезаписан при запуске)
RUN echo "agent_id: temp-agent\ncentral_server: http://localhost:8000\nagent_token: temp-token\nvmid: 1" > config.yml

# Команда запуска
CMD ["python3", "agent.py"]
