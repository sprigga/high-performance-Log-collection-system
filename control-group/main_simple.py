"""
對照組 - 簡化版 FastAPI 應用
直接寫入 PostgreSQL，無負載平衡、連接池、Redis、Worker
"""
import os
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import Json
# 新增: Prometheus 監控支援
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import psutil

# ==========================================
# 應用程式初始化
# ==========================================
app = FastAPI(
    title="對照組 - 簡化日誌收集系統",
    description="直接寫入 PostgreSQL，無優化機制",
    version="1.0.0"
)

# ==========================================
# Prometheus 監控指標定義
# ==========================================
# HTTP 請求相關
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

# 日誌業務指標
logs_received_total = Counter(
    'logs_received_total',
    'Total logs received',
    ['device_id', 'log_level']
)
logs_processing_errors_total = Counter(
    'logs_processing_errors_total',
    'Total log processing errors',
    ['error_type']
)
batch_processing_duration_seconds = Histogram(
    'batch_processing_duration_seconds',
    'Batch processing duration',
    ['batch_size']
)

# PostgreSQL 指標
postgres_connection_duration_seconds = Histogram(
    'postgres_connection_duration_seconds',
    'PostgreSQL connection duration'
)
postgres_query_duration_seconds = Histogram(
    'postgres_query_duration_seconds',
    'PostgreSQL query duration',
    ['operation']
)

# 系統資源指標
system_cpu_usage_percent = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage'
)
system_memory_usage_bytes = Gauge(
    'system_memory_usage_bytes',
    'System memory usage in bytes',
    ['type']
)
system_disk_usage_bytes = Gauge(
    'system_disk_usage_bytes',
    'System disk usage in bytes',
    ['type']
)

# ==========================================
# 更新系統指標函數
# ==========================================
def update_system_metrics():
    """更新系統資源指標"""
    try:
        # CPU 使用率
        cpu_percent = psutil.cpu_percent(interval=0.1)
        system_cpu_usage_percent.set(cpu_percent)

        # 記憶體使用
        memory = psutil.virtual_memory()
        system_memory_usage_bytes.labels(type='used').set(memory.used)
        system_memory_usage_bytes.labels(type='available').set(memory.available)
        system_memory_usage_bytes.labels(type='total').set(memory.total)

        # 磁碟使用
        disk = psutil.disk_usage('/')
        system_disk_usage_bytes.labels(type='used').set(disk.used)
        system_disk_usage_bytes.labels(type='free').set(disk.free)
        system_disk_usage_bytes.labels(type='total').set(disk.total)
    except Exception as e:
        print(f"更新系統指標失敗: {e}")

# ==========================================
# PostgreSQL 配置（無連接池）
# ==========================================
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'loguser')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'logpass')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'logsdb')

# ==========================================
# Pydantic 模型
# ==========================================
class LogEntryRequest(BaseModel):
    """日誌請求模型"""
    device_id: str = Field(..., min_length=1, max_length=50)
    log_level: str
    message: str = Field(..., min_length=1, max_length=5000)
    log_data: Optional[dict] = Field(default={})

class BatchLogEntryRequest(BaseModel):
    """批量日誌請求模型"""
    logs: list[LogEntryRequest] = Field(..., min_length=1, max_length=1000)

class LogEntryResponse(BaseModel):
    """日誌回應模型"""
    status: str
    log_id: Optional[int] = None
    received_at: datetime

class BatchLogEntryResponse(BaseModel):
    """批量日誌回應模型"""
    status: str
    count: int
    received_at: datetime

# ==========================================
# 資料庫連線函數（每次請求創建新連線）
# ==========================================
def get_db_connection():
    """
    創建新的資料庫連線（無連接池）
    每次請求都會創建和關閉連線
    """
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB
    )

# ==========================================
# API 端點 - 單筆日誌（直接寫入）
# ==========================================
@app.post("/api/log", response_model=LogEntryResponse)
async def create_log(log: LogEntryRequest):
    """
    接收日誌並直接寫入 PostgreSQL

    流程：
    1. 驗證日誌格式
    2. 創建資料庫連線
    3. 直接 INSERT 到資料庫
    4. 關閉連線
    5. 返回結果

    無優化：每次請求都創建新連線
    """
    # 記錄業務指標
    logs_received_total.labels(
        device_id=log.device_id,
        log_level=log.log_level
    ).inc()

    # 記錄請求時間
    start_time = time.time()

    try:
        # 每次請求創建新連線（無連接池）
        # 記錄連線時間
        conn_start = time.time()
        conn = get_db_connection()
        postgres_connection_duration_seconds.observe(time.time() - conn_start)

        cursor = conn.cursor()

        # 直接 INSERT 到資料庫
        insert_query = """
            INSERT INTO logs (device_id, log_level, message, log_data, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """

        # 記錄查詢時間
        query_start = time.time()
        cursor.execute(
            insert_query,
            (
                log.device_id,
                log.log_level,
                log.message,
                Json(log.log_data) if log.log_data else Json({}),
                datetime.now(ZoneInfo("Asia/Taipei"))
            )
        )
        postgres_query_duration_seconds.labels(operation='insert').observe(time.time() - query_start)

        log_id = cursor.fetchone()[0]

        # 提交事務
        conn.commit()

        # 關閉連線
        cursor.close()
        conn.close()

        # 記錄HTTP請求指標
        http_requests_total.labels(method='POST', endpoint='/api/log', status='200').inc()
        http_request_duration_seconds.labels(method='POST', endpoint='/api/log').observe(time.time() - start_time)

        return LogEntryResponse(
            status="saved",
            log_id=log_id,
            received_at=datetime.now()
        )

    except Exception as e:
        logs_processing_errors_total.labels(error_type='database_write').inc()
        http_requests_total.labels(method='POST', endpoint='/api/log', status='500').inc()
        print(f"寫入資料庫失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save log: {str(e)}")

# ==========================================
# API 端點 - 批量日誌（直接寫入）
# ==========================================
@app.post("/api/logs/batch", response_model=BatchLogEntryResponse)
async def create_batch_logs(batch: BatchLogEntryRequest):
    """
    批量接收日誌並直接寫入 PostgreSQL

    流程：
    1. 驗證日誌格式
    2. 創建資料庫連線
    3. 使用 executemany 批量插入
    4. 關閉連線
    5. 返回結果

    無優化：每次請求都創建新連線，無非同步處理
    """
    batch_size = len(batch.logs)
    start_time = time.time()

    try:
        # 記錄業務指標
        for log in batch.logs:
            logs_received_total.labels(
                device_id=log.device_id,
                log_level=log.log_level
            ).inc()

        # 每次請求創建新連線（無連接池）
        conn_start = time.time()
        conn = get_db_connection()
        postgres_connection_duration_seconds.observe(time.time() - conn_start)

        cursor = conn.cursor()

        # 準備批量插入的資料
        current_time = datetime.now(ZoneInfo("Asia/Taipei"))
        values = [
            (
                log.device_id,
                log.log_level,
                log.message,
                Json(log.log_data) if log.log_data else Json({}),
                current_time
            )
            for log in batch.logs
        ]

        # 批量 INSERT
        insert_query = """
            INSERT INTO logs (device_id, log_level, message, log_data, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """

        # 記錄查詢時間
        query_start = time.time()
        cursor.executemany(insert_query, values)
        postgres_query_duration_seconds.labels(operation='batch_insert').observe(time.time() - query_start)

        # 提交事務
        conn.commit()

        # 關閉連線
        cursor.close()
        conn.close()

        # 記錄批量處理時間
        duration = time.time() - start_time
        batch_processing_duration_seconds.labels(batch_size=str(batch_size)).observe(duration)

        # 記錄HTTP請求指標
        http_requests_total.labels(method='POST', endpoint='/api/logs/batch', status='200').inc()
        http_request_duration_seconds.labels(method='POST', endpoint='/api/logs/batch').observe(duration)

        return BatchLogEntryResponse(
            status="saved",
            count=batch_size,
            received_at=datetime.now()
        )

    except Exception as e:
        logs_processing_errors_total.labels(error_type='batch_database_write').inc()
        http_requests_total.labels(method='POST', endpoint='/api/logs/batch', status='500').inc()
        print(f"批量寫入資料庫失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save batch logs: {str(e)}")

# ==========================================
# API 端點 - 健康檢查
# ==========================================
@app.get("/health")
async def health_check():
    """簡單的健康檢查"""
    try:
        conn = get_db_connection()
        conn.close()
        return {
            "status": "healthy",
            "instance": "simple-fastapi",
            "checks": {"postgres": True}
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "instance": "simple-fastapi",
            "checks": {"postgres": False},
            "error": str(e)
        }

# ==========================================
# API 端點 - Prometheus Metrics
# ==========================================
@app.get("/metrics")
async def metrics():
    """Prometheus metrics 端點"""
    # 更新系統指標
    update_system_metrics()
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

# ==========================================
# API 端點 - 根路徑
# ==========================================
@app.get("/")
async def root():
    """API 根路徑"""
    return {
        "service": "對照組 - 簡化日誌收集系統",
        "version": "1.0.0",
        "description": "直接寫入 PostgreSQL，無負載平衡、連接池、Redis、Worker",
        "endpoints": {
            "health": "/health",
            "create_log": "POST /api/log",
            "create_batch_logs": "POST /api/logs/batch",
            "metrics": "/metrics",
            "docs": "/docs"
        }
    }

# ==========================================
# 應用程式生命週期
# ==========================================
@app.on_event("startup")
async def startup_event():
    """應用程式啟動時執行"""
    print("🚀 啟動對照組 FastAPI 實例")
    # 初始化系統指標
    update_system_metrics()
    print("✅ 系統指標監控已啟動")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_simple:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1
    )
