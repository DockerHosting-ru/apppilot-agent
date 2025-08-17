# AppPilot Agent

Агент для платформы AppPilot с поддержкой Docker Compose для развертывания multi-container приложений.

## Возможности

* Развертывание приложений через Docker Compose
* Поддержка multi-container приложений
* Автоматическое назначение портов
* Развертывание на основе шаблонов
* JWT аутентификация
* Мониторинг состояния здоровья

## Быстрый старт

### Установка зависимостей
```bash
pip install -r requirements.txt
```

### Запуск агента
```bash
python agent_compose_support.py
```

## Конфигурация

Установите переменные окружения:

* `API_SERVER_URL` - URL сервера AppPilot API
* `AGENT_ID` - Уникальный идентификатор агента
* `JWT_TOKEN` - Токен аутентификации

## Docker

### Сборка образа
```bash
docker build -t apppilot-agent .
```

### Запуск контейнера
```bash
docker run -d --name apppilot-agent apppilot-agent
```

## Шаблоны

Агент поддерживает следующие шаблоны:

* **100** - n8n с PostgreSQL
* **101** - WordPress с MySQL  
* **102** - Nextcloud с PostgreSQL

## Лицензия

MIT License

## О проекте

AppPilot Platform - система управления развертыванием приложений

[dockerhosting.ru](https://dockerhosting.ru)
