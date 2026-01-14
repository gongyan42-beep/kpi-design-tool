FROM python:3.11-slim

WORKDIR /app

# 设置时区为北京时间
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建数据目录
RUN mkdir -p data

# 暴露端口
EXPOSE 3014

# 启动命令（gunicorn + gevent 高并发模式）
# -w 4: 4个 worker 进程
# -k gevent: 使用协程处理 I/O 密集型任务
# --timeout 120: AI 响应可能较慢，设置 120 秒超时
# --worker-connections 100: 每个 worker 最多处理 100 个并发连接
CMD ["gunicorn", "-w", "4", "-k", "gevent", "-b", "0.0.0.0:3014", "--timeout", "120", "--worker-connections", "100", "app:app"]
