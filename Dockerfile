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
RUN mkdir -p /opt/appliku /opt/appliku/apps /var/log

# Копирование файлов агента
COPY agent_compose_support.py /opt/appliku/agent.py
COPY requirements.txt /opt/appliku/

# Установка Python зависимостей
RUN pip install --no-cache-dir -r /opt/appliku/requirements.txt

# Установка прав
RUN chown -R appliku:appliku /opt/appliku /var/log

# Переключение на пользователя appliku
USER appliku

# Рабочая директория
WORKDIR /opt/appliku

# Создание конфигурационного файла (будет перезаписан при запуске)
RUN echo "agent_id: temp-agent\ncentral_server: http://localhost:8000\nagent_token: temp-token\nvps_id: 1" > config.yml

# Команда запуска
CMD ["python3", "agent.py"]
