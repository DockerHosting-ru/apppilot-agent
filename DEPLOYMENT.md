# Инструкции по развертыванию AppPilot Agent

## Предварительные требования

- Python 3.11+
- Docker Engine
- Docker Compose
- Git

## Способ 1: Прямая установка

### 1. Клонирование репозитория
```bash
git clone https://github.com/DockerHosting-ru/apppilot-agent.git
cd apppilot-agent
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Настройка переменных окружения
```bash
cp env.example .env
# Отредактируйте .env файл с вашими настройками
```

### 4. Запуск агента
```bash
chmod +x run.sh
./run.sh
```

## Способ 2: Docker Compose

### 1. Клонирование и настройка
```bash
git clone https://github.com/DockerHosting-ru/apppilot-agent.git
cd apppilot-agent
cp env.example .env
# Отредактируйте .env файл
```

### 2. Запуск через Docker Compose
```bash
docker compose up -d
```

### 3. Просмотр логов
```bash
docker compose logs -f apppilot-agent
```

## Способ 3: Прямой Docker

### 1. Сборка образа
```bash
docker build -t apppilot-agent .
```

### 2. Запуск контейнера
```bash
docker run -d \
  --name apppilot-agent \
  -e API_SERVER_URL=http://your-api-server:8000 \
  -e AGENT_ID=your-agent-id \
  -e JWT_TOKEN=your-jwt-token \
  -v /var/run/docker.sock:/var/run/docker.sock \
  apppilot-agent
```

## Настройка переменных окружения

### Обязательные переменные
- `JWT_TOKEN` - Токен аутентификации от AppPilot API

### Опциональные переменные
- `API_SERVER_URL` - URL API сервера (по умолчанию: http://31.169.124.43:8000)
- `AGENT_ID` - ID агента (по умолчанию: test-agent-001)
- `POLL_INTERVAL` - Интервал опроса в секундах (по умолчанию: 5)
- `PORT_RANGE_START` - Начало диапазона портов (по умолчанию: 8001)
- `PORT_RANGE_END` - Конец диапазона портов (по умолчанию: 9000)

## Проверка работы

### 1. Проверка статуса агента
```bash
docker ps | grep apppilot-agent
```

### 2. Просмотр логов
```bash
docker logs apppilot-agent
```

### 3. Проверка подключения к Docker
```bash
docker exec apppilot-agent docker ps
```

## Устранение неполадок

### Агент не подключается к API
- Проверьте правильность `API_SERVER_URL`
- Убедитесь, что `JWT_TOKEN` действителен
- Проверьте доступность API сервера

### Ошибки Docker
- Убедитесь, что Docker Engine запущен
- Проверьте права доступа к Docker socket
- Проверьте свободное место на диске

### Проблемы с портами
- Проверьте диапазон портов в переменных окружения
- Убедитесь, что порты не заняты другими сервисами

## Обновление агента

### 1. Остановка текущего агента
```bash
docker compose down
# или
docker stop apppilot-agent
```

### 2. Обновление кода
```bash
git pull origin main
```

### 3. Пересборка и запуск
```bash
docker compose up -d --build
```
