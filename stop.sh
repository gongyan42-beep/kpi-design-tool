#!/bin/bash

# 停止脚本

cd "$(dirname "$0")"

PORT=$(grep PORT .env | cut -d '=' -f2)
PORT=${PORT:-5009}

echo "🛑 停止服务..."
lsof -ti:$PORT | xargs kill -9 2>/dev/null

echo "✅ 服务已停止"
