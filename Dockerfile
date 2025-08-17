FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Docker CLI
RUN curl -fsSL https://get.docker.com/builds/Linux/x86_64/docker-latest.tgz | tar -xzC /usr/local/bin --strip=1 docker/docker

# Устанавливаем Docker Compose
RUN curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose \
    && chmod +x /usr/local/bin/docker-compose

# Создаем группу docker и пользователя appliku
RUN groupadd -r docker && \
    useradd -m -s /bin/bash appliku && \
    usermod -aG docker appliku

# Создаем рабочую директорию
WORKDIR /opt/appliku

# Копируем код агента с РЕАЛЬНЫМ развертыванием
COPY agent_real_deployment.py /opt/appliku/agent.py
COPY requirements.txt /opt/appliku/

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Создаем директории для приложений и логов
RUN mkdir -p /opt/appliku/apps /opt/appliku/logs \
    && chown -R appliku:appliku /opt/appliku

# Переключаемся на пользователя appliku
USER appliku

# Запускаем агент с реальным развертыванием
CMD ["python", "agent.py"]
