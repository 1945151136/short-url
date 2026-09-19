# ===== 短链接服务 Web 镜像（Django + gunicorn）=====
FROM python:3.12-slim

# 让 Python 日志直出、不生成 .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl 用于容器内健康自检
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "gunicorn>=21.2"

# 拷贝项目代码
COPY . .

EXPOSE 8000

# 等待数据库 -> 迁移 -> 收集静态文件 -> 启动 gunicorn
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
