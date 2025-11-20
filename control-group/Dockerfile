FROM python:3.11-slim

WORKDIR /app

# 安裝必要的套件
# 註釋: 新增 prometheus_client 和 psutil 以支援監控
# RUN pip install --no-cache-dir \
#     fastapi==0.104.1 \
#     uvicorn[standard]==0.24.0 \
#     psycopg2-binary==2.9.9 \
#     pydantic==2.5.0
RUN pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    psycopg2-binary==2.9.9 \
    pydantic==2.5.0 \
    prometheus-client==0.19.0 \
    psutil==5.9.6

# 複製應用程式
COPY main_simple.py .

# 暴露端口
EXPOSE 8000

# 啟動命令（單一 worker，無優化）
CMD ["uvicorn", "main_simple:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
