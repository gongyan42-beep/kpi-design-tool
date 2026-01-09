#!/bin/bash

# 猫课电商管理落地班核心工具 - 启动脚本

cd "$(dirname "$0")"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "📦 检查依赖..."
pip install -r requirements.txt -q

# 确保数据目录存在
mkdir -p data

# 获取端口
PORT=$(grep KPI_PORT .env | cut -d '=' -f2)
PORT=${PORT:-5009}

echo ""
echo "🚀 启动猫课电商管理落地班核心工具..."
echo "📍 访问地址: http://localhost:$PORT"
echo ""

# 启动应用（使用gunicorn避免Python 3.14兼容问题）
gunicorn -b 0.0.0.0:$PORT app:app &
PID=$!

# 等待启动
sleep 2

# 打开浏览器
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "http://localhost:$PORT"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open "http://localhost:$PORT" 2>/dev/null || echo "请手动打开浏览器访问 http://localhost:$PORT"
fi

echo "✅ 服务已启动 (PID: $PID)"
echo "🛑 停止服务请运行: ./stop.sh"

# 等待进程
wait $PID
