#!/bin/sh
# Web 容器启动脚本：(MySQL 模式)等待数据库 -> 迁移 -> 收集静态资源 -> 启动 gunicorn
set -e

# 仅在使用 MySQL 时等待数据库就绪；SQLite 模式（DB_ENGINE 非 mysql）直接跳过
if [ "${DB_ENGINE:-mysql}" = "mysql" ]; then
echo "[entrypoint] 等待 MySQL ${DB_HOST:-db}:${DB_PORT:-3306} 就绪 ..."
python - <<'PY'
import os
import sys
import time

import pymysql

host = os.getenv('DB_HOST', 'db')
port = int(os.getenv('DB_PORT', '3306'))
user = os.getenv('DB_USER', 'shorturl')
password = os.getenv('DB_PASSWORD', 'shorturl_pass')

for i in range(60):
    try:
        conn = pymysql.connect(host=host, port=port, user=user,
                               password=password, connect_timeout=3)
        conn.close()
        print('[entrypoint] MySQL 已就绪')
        break
    except Exception as exc:  # noqa: BLE001
        print(f'[entrypoint] 等待数据库中 ... ({i + 1}/60) {exc}')
        time.sleep(2)
else:
    print('[entrypoint] 等待 MySQL 超时，退出')
    sys.exit(1)
PY
else
echo "[entrypoint] 使用 SQLite（DB_ENGINE 非 mysql），跳过数据库就绪等待"
fi

echo "[entrypoint] 执行数据库迁移 migrate ..."
python manage.py migrate --noinput

echo "[entrypoint] 收集静态文件 collectstatic ..."
python manage.py collectstatic --noinput

echo "[entrypoint] 启动 gunicorn (workers=${GUNICORN_WORKERS:-3}) ..."
# PORT 由 Render 等 PaaS 注入；本地 / Compose 默认 8000
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
