# This file is unrelated to image name.
FROM python:3.12-slim

# 不生成 __pycache__ 和 .pyc 文件，减少容器里的临时文件
# 让 Python 日志直接输出到控制台，不缓存。这样 docker logs 能及时看到日志
# pip 安装依赖时不保留缓存，减少镜像体积
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 容器目录 -w /app
WORKDIR /app

# 复制到容器目录下
COPY requirements.txt .
COPY packages/ /packages/

# 在构建镜像时安装 Python 依赖
RUN python -m pip install --no-index --find-links=/packages -r requirements.txt

# 把当前项目所有目录复制到容器 /app 目录下
COPY . .

# 容器监听 5000 端口
EXPOSE 5000

# 启动命令，使用 uvicorn 运行 FastAPI 应用，容器监听在自己的 5000 端口，单 worker 模式（如果需要生产环境部署，建议使用多 worker 模式或者配合 Gunicorn）
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]