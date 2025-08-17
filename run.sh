#!/bin/bash

# AppPilot Agent Runner Script

echo "🚀 Запуск AppPilot Agent..."

# Проверяем наличие переменных окружения
if [ -z "$JWT_TOKEN" ]; then
    echo "❌ Ошибка: JWT_TOKEN не установлен"
    echo "Установите переменную окружения JWT_TOKEN"
    exit 1
fi

if [ -z "$API_SERVER_URL" ]; then
    echo "⚠️  Предупреждение: API_SERVER_URL не установлен, используется значение по умолчанию"
    export API_SERVER_URL="http://31.169.124.43:8000"
fi

if [ -z "$AGENT_ID" ]; then
    echo "⚠️  Предупреждение: AGENT_ID не установлен, используется значение по умолчанию"
    export AGENT_ID="test-agent-001"
fi

echo "✅ Конфигурация:"
echo "   API Server: $API_SERVER_URL"
echo "   Agent ID: $AGENT_ID"
echo "   Poll Interval: ${POLL_INTERVAL:-5}s"

# Запускаем агент
echo "🎯 Запуск агента..."
python agent_compose_support.py
