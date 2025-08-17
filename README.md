# AppPilot Agent

Агент для платформы AppPilot с поддержкой Docker Compose для развертывания multi-container приложений.

Docker Compose deployment agent for AppPilot platform.

## Возможности / Features

* Развертывание приложений через Docker Compose
* Поддержка multi-container приложений
* Автоматическое назначение портов
* Развертывание на основе шаблонов
* JWT аутентификация
* Мониторинг состояния здоровья

- Docker Compose application deployment
- Multi-container application support
- Automatic port assignment
- Template-based deployments
- JWT authentication
- Health monitoring

## Быстрый старт / Quick Start

### Установка зависимостей / Install dependencies
```bash
pip install -r requirements.txt
```

### Запуск агента / Run agent
```bash
python agent_compose_support.py
```

## Конфигурация / Configuration

Установите переменные окружения / Set environment variables:

* `API_SERVER_URL` - URL сервера AppPilot API
* `AGENT_ID` - Уникальный идентификатор агента
* `JWT_TOKEN` - Токен аутентификации

- `API_SERVER_URL` - AppPilot API server URL
- `AGENT_ID` - Unique agent identifier
- `JWT_TOKEN` - Authentication token

## Docker

### Сборка образа / Build image
```bash
docker build -t apppilot-agent .
```

### Запуск контейнера / Run container
```bash
docker run -d --name apppilot-agent apppilot-agent
```

## Шаблоны / Templates

Агент поддерживает следующие шаблоны / Agent supports the following templates:

* **100** - n8n с PostgreSQL
* **101** - WordPress с MySQL  
* **102** - Nextcloud с PostgreSQL

## Лицензия / License

MIT License

## О проекте / About

AppPilot Platform - система управления развертыванием приложений

AppPilot Platform - application deployment management system

[dockerhosting.ru](https://dockerhosting.ru)
