FROM python:3.11-slim

WORKDIR /app

# 注意：构建上下文是仓库根目录（见 deploy/docker-compose.yml 的 build.context: ..）。
# 预测功能需要 workflow/ 与 social_forecast/，它们与 backend/ 同级，所以不能只用 backend/ 作上下文。
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 预测功能的重依赖（CPU 版 torch 约 1 GB）。默认不装，不跑预测的镜像保持精简：
#   docker compose build --build-arg INSTALL_FORECAST_DEPS=1 backend
ARG INSTALL_FORECAST_DEPS=0
COPY social_forecast/requirements.txt ./forecast-requirements.txt
RUN if [ "$INSTALL_FORECAST_DEPS" = "1" ]; then \
        pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch && \
        pip install --no-cache-dir -r forecast-requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple; \
    fi

COPY backend/ ./
COPY workflow/ ./workflow/
COPY social_forecast/ ./social_forecast/

EXPOSE 5000

# 单 worker：预测服务按进程加载模型（CPU torch + 权重常驻约 265 MiB/进程），
# -w 4 会把 2 GB 机器直接打满。并发由 Nginx 队列和后台任务闸门控制，不靠加 worker。
# 权重目录不进镜像，运行时挂载（见 compose 的 FORECAST_CHECKPOINT）。
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "--timeout", "120", "run:app"]
