# ===== 阶段 1：构建依赖层 =====
# 使用官方 Python 轻量镜像作为基础
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /app

# 设置环境变量，避免 Python 生成 .pyc 文件并实时刷新日志
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安装系统依赖：
# - build-essential / pkg-config：编译部分 Python 扩展所需
# - libpq-dev：asyncpg / psycopg 连接 PostgreSQL 所需
# - libxml2 / libxslt：部分文档解析库依赖
# - libjpeg / zlib：PyPDF2、python-docx 解析图像型文档所需
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libpq-dev \
        libxml2-dev \
        libxslt1-dev \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# 先单独复制 requirements.txt，利用 Docker 层缓存机制加速构建
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ===== 阶段 2：运行时镜像 =====
# 运行阶段同样使用轻量镜像，减小最终镜像体积
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 运行时仅需动态链接库（无需编译工具链）：
# - libpq5：asyncpg 运行时依赖
# - libxml2 / libxslt / libjpeg / zlib：文档解析运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libxml2 \
        libxslt1.1 \
        libjpeg62-turbo \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制已安装的 Python 第三方库
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制应用源码
COPY app/ ./app/

# 暴露 FastAPI 服务端口
EXPOSE 8000

# 启动 uvicorn 服务
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
