# 系統監控工具完整指南

## 📋 目錄
1. [Prometheus + Grafana 監控方案](#prometheus--grafana-監控方案)
2. [即時系統監控工具](#即時系統監控工具)
3. [日誌分析工具](#日誌分析工具)
4. [容器監控](#容器監控)
5. [完整監控架構](#完整監控架構)
6. [告警配置](#告警配置)

---

## Prometheus + Grafana 監控方案

### 1. Prometheus 配置

#### 基礎配置文件

```yaml
# prometheus.yml
global:
  scrape_interval: 15s      # 每 15 秒抓取一次指標
  evaluation_interval: 15s   # 每 15 秒評估一次告警規則
  
  external_labels:
    cluster: 'log-collection-system'
    environment: 'production'

# 告警管理器配置
alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

# 告警規則文件
rule_files:
  - "alerts/*.yml"

# 抓取配置
scrape_configs:
  # FastAPI 應用程式監控
  - job_name: 'fastapi'
    static_configs:
      - targets: 
        - 'fastapi-1:8000'
        - 'fastapi-2:8000'
        - 'fastapi-3:8000'
    metrics_path: '/metrics'
    scrape_interval: 5s
    
  # Redis 監控
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
    scrape_interval: 10s
  
  # PostgreSQL 監控
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']
    scrape_interval: 10s
  
  # Nginx 監控
  - job_name: 'nginx'
    static_configs:
      - targets: ['nginx-exporter:9113']
    scrape_interval: 10s
  
  # Node Exporter (系統資源監控)
  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']
    scrape_interval: 10s
  
  # Worker 監控
  - job_name: 'worker'
    static_configs:
      - targets:
        - 'worker-1:8001'
        - 'worker-2:8001'
    metrics_path: '/metrics'
    scrape_interval: 10s
```

#### Docker Compose 配置

```yaml
# docker-compose.yml 中加入監控服務
version: '3.8'

services:
  # ... 其他服務 ...
  
  # Prometheus
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus/alerts:/etc/prometheus/alerts
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
    networks:
      - monitoring
    restart: unless-stopped
  
  # Grafana
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin123
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/dashboards:/var/lib/grafana/dashboards
    depends_on:
      - prometheus
    networks:
      - monitoring
    restart: unless-stopped
  
  # AlertManager
  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    networks:
      - monitoring
    restart: unless-stopped
  
  # Redis Exporter
  redis-exporter:
    image: oliver006/redis_exporter:latest
    container_name: redis-exporter
    ports:
      - "9121:9121"
    environment:
      - REDIS_ADDR=redis:6379
    depends_on:
      - redis
    networks:
      - monitoring
    restart: unless-stopped
  
  # PostgreSQL Exporter
  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:latest
    container_name: postgres-exporter
    ports:
      - "9187:9187"
    environment:
      - DATA_SOURCE_NAME=postgresql://user:pass@postgres:5432/logs_db?sslmode=disable
    depends_on:
      - postgres
    networks:
      - monitoring
    restart: unless-stopped
  
  # Nginx Exporter
  nginx-exporter:
    image: nginx/nginx-prometheus-exporter:latest
    container_name: nginx-exporter
    ports:
      - "9113:9113"
    command:
      - '-nginx.scrape-uri=http://nginx:80/stub_status'
    depends_on:
      - nginx
    networks:
      - monitoring
    restart: unless-stopped
  
  # Node Exporter
  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--path.rootfs=/rootfs'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    networks:
      - monitoring
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
  alertmanager_data:

networks:
  monitoring:
    driver: bridge
```

### 2. FastAPI 應用程式指標整合

#### 完整的 metrics.py 模組

```python
# metrics.py
from prometheus_client import (
    Counter, Histogram, Gauge, Summary,
    generate_latest, CONTENT_TYPE_LATEST
)
from fastapi import Response
import time
import psutil
import functools

# ==================== HTTP 請求指標 ====================
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

http_request_size_bytes = Summary(
    'http_request_size_bytes',
    'HTTP request size in bytes',
    ['method', 'endpoint']
)

http_response_size_bytes = Summary(
    'http_response_size_bytes',
    'HTTP response size in bytes',
    ['method', 'endpoint']
)

# ==================== Redis 指標 ====================
redis_stream_messages_total = Counter(
    'redis_stream_messages_total',
    'Total messages written to Redis Stream',
    ['status']  # success, failed
)

redis_stream_size = Gauge(
    'redis_stream_size',
    'Current size of Redis Stream'
)

redis_cache_hits_total = Counter(
    'redis_cache_hits_total',
    'Total Redis cache hits'
)

redis_cache_misses_total = Counter(
    'redis_cache_misses_total',
    'Total Redis cache misses'
)

redis_operation_duration_seconds = Histogram(
    'redis_operation_duration_seconds',
    'Redis operation duration',
    ['operation'],  # xadd, get, set, xreadgroup
    buckets=(0.0001, 0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1)
)

# ==================== 資料庫指標 ====================
db_connections_active = Gauge(
    'db_connections_active',
    'Active database connections',
    ['pool']  # master, replica
)

db_connections_idle = Gauge(
    'db_connections_idle',
    'Idle database connections',
    ['pool']
)

db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query duration',
    ['query_type', 'pool'],  # select, insert, update, delete
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

db_queries_total = Counter(
    'db_queries_total',
    'Total database queries',
    ['query_type', 'status']  # success, error
)

# ==================== 業務指標 ====================
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
    ['batch_size'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
)

active_devices_total = Gauge(
    'active_devices_total',
    'Total number of active devices'
)

# ==================== 系統資源指標 ====================
system_cpu_usage_percent = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage'
)

system_memory_usage_bytes = Gauge(
    'system_memory_usage_bytes',
    'System memory usage in bytes',
    ['type']  # used, available, total
)

system_disk_usage_bytes = Gauge(
    'system_disk_usage_bytes',
    'System disk usage in bytes',
    ['type']  # used, free, total
)

# ==================== Worker 指標 ====================
worker_active_tasks = Gauge(
    'worker_active_tasks',
    'Number of active worker tasks',
    ['worker_id']
)

worker_processed_logs_total = Counter(
    'worker_processed_logs_total',
    'Total logs processed by worker',
    ['worker_id', 'status']  # success, failed
)

worker_batch_size = Histogram(
    'worker_batch_size',
    'Worker batch size distribution',
    buckets=(10, 25, 50, 100, 200, 500, 1000)
)


# ==================== 裝飾器和輔助函數 ====================
def track_time(metric: Histogram, labels: dict = None):
    """追蹤函數執行時間的裝飾器"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
        
        # 根據函數類型返回對應的包裝器
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def update_system_metrics():
    """更新系統資源指標"""
    # CPU 使用率
    cpu_percent = psutil.cpu_percent(interval=1)
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


class MetricsMiddleware:
    """FastAPI 中間件用於自動記錄 HTTP 指標"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        start_time = time.time()
        
        # 記錄請求大小
        request_size = 0
        
        async def receive_with_size():
            nonlocal request_size
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                request_size += len(body)
            return message
        
        # 記錄回應大小
        response_size = 0
        status_code = 500
        
        async def send_with_size(message):
            nonlocal response_size, status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                response_size += len(body)
            await send(message)
        
        try:
            await self.app(scope, receive_with_size, send_with_size)
        finally:
            # 記錄指標
            duration = time.time() - start_time
            method = scope["method"]
            path = scope["path"]
            
            http_requests_total.labels(
                method=method,
                endpoint=path,
                status=status_code
            ).inc()
            
            http_request_duration_seconds.labels(
                method=method,
                endpoint=path
            ).observe(duration)
            
            http_request_size_bytes.labels(
                method=method,
                endpoint=path
            ).observe(request_size)
            
            http_response_size_bytes.labels(
                method=method,
                endpoint=path
            ).observe(response_size)
```

#### 在 FastAPI 中使用 Metrics

```python
# main.py
from fastapi import FastAPI, Response
from metrics import (
    MetricsMiddleware,
    generate_latest,
    CONTENT_TYPE_LATEST,
    logs_received_total,
    redis_stream_messages_total,
    update_system_metrics,
    track_time,
    redis_operation_duration_seconds
)
import asyncio

app = FastAPI(title="Log Collection API")

# 加入 Metrics 中間件
app.add_middleware(MetricsMiddleware)

# 背景任務：定期更新系統指標
async def update_metrics_task():
    """背景任務：定期更新系統指標"""
    while True:
        update_system_metrics()
        await asyncio.sleep(15)  # 每 15 秒更新一次

@app.on_event("startup")
async def startup_event():
    """啟動時開始背景任務"""
    asyncio.create_task(update_metrics_task())

@app.post("/api/log")
async def create_log(log: LogEntry):
    """接收日誌並快速寫入 Redis Stream"""
    # 記錄業務指標
    logs_received_total.labels(
        device_id=log.device_id,
        log_level=log.log_level
    ).inc()
    
    # 準備資料
    log_dict = {
        "device_id": log.device_id,
        "log_level": log.log_level,
        "message": log.message,
        "log_data": json.dumps(log.log_data),
        "timestamp": datetime.now().isoformat()
    }
    
    # 追蹤 Redis 操作時間
    start_time = time.time()
    try:
        # 寫入 Redis Stream
        message_id = await redis_client.xadd(
            "logs:stream",
            log_dict,
            maxlen=100000
        )
        
        # 記錄成功
        redis_stream_messages_total.labels(status='success').inc()
        
        # 記錄操作時間
        duration = time.time() - start_time
        redis_operation_duration_seconds.labels(operation='xadd').observe(duration)
        
        return LogResponse(status="queued", message_id=message_id)
    
    except Exception as e:
        redis_stream_messages_total.labels(status='failed').inc()
        raise

@app.get("/metrics")
async def metrics():
    """Prometheus metrics 端點"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {"status": "healthy"}
```

### 3. Grafana 儀表板配置

#### 自動配置 Datasource

```yaml
# grafana/provisioning/datasources/prometheus.yml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
    jsonData:
      timeInterval: "15s"
```

#### 預設儀表板配置

```yaml
# grafana/provisioning/dashboards/default.yml
apiVersion: 1

providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
```

#### 完整儀表板 JSON

```json
{
  "dashboard": {
    "title": "日誌收集系統效能儀表板",
    "timezone": "browser",
    "refresh": "10s",
    "time": {
      "from": "now-1h",
      "to": "now"
    },
    "panels": [
      {
        "id": 1,
        "title": "每秒請求數 (QPS)",
        "type": "graph",
        "gridPos": {
          "x": 0,
          "y": 0,
          "w": 12,
          "h": 8
        },
        "targets": [
          {
            "expr": "sum(rate(http_requests_total[1m]))",
            "legendFormat": "總 QPS",
            "refId": "A"
          },
          {
            "expr": "sum(rate(http_requests_total{status=~\"2..\"}[1m]))",
            "legendFormat": "成功請求",
            "refId": "B"
          },
          {
            "expr": "sum(rate(http_requests_total{status=~\"5..\"}[1m]))",
            "legendFormat": "錯誤請求",
            "refId": "C"
          }
        ],
        "yaxes": [
          {
            "format": "reqps",
            "label": "請求/秒"
          }
        ]
      },
      {
        "id": 2,
        "title": "HTTP 請求延遲 (P50, P95, P99)",
        "type": "graph",
        "gridPos": {
          "x": 12,
          "y": 0,
          "w": 12,
          "h": 8
        },
        "targets": [
          {
            "expr": "histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
            "legendFormat": "P50",
            "refId": "A"
          },
          {
            "expr": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
            "legendFormat": "P95",
            "refId": "B"
          },
          {
            "expr": "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
            "legendFormat": "P99",
            "refId": "C"
          }
        ],
        "yaxes": [
          {
            "format": "s",
            "label": "延遲時間"
          }
        ]
      },
      {
        "id": 3,
        "title": "Redis Stream 大小",
        "type": "graph",
        "gridPos": {
          "x": 0,
          "y": 8,
          "w": 8,
          "h": 8
        },
        "targets": [
          {
            "expr": "redis_stream_size",
            "legendFormat": "Stream 長度",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "short",
            "label": "訊息數量"
          }
        ]
      },
      {
        "id": 4,
        "title": "Redis 快取命中率",
        "type": "graph",
        "gridPos": {
          "x": 8,
          "y": 8,
          "w": 8,
          "h": 8
        },
        "targets": [
          {
            "expr": "rate(redis_cache_hits_total[5m]) / (rate(redis_cache_hits_total[5m]) + rate(redis_cache_misses_total[5m])) * 100",
            "legendFormat": "快取命中率",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "percent",
            "label": "命中率",
            "max": 100,
            "min": 0
          }
        ]
      },
      {
        "id": 5,
        "title": "資料庫連線數",
        "type": "graph",
        "gridPos": {
          "x": 16,
          "y": 8,
          "w": 8,
          "h": 8
        },
        "targets": [
          {
            "expr": "db_connections_active",
            "legendFormat": "活動連線 - {{pool}}",
            "refId": "A"
          },
          {
            "expr": "db_connections_idle",
            "legendFormat": "閒置連線 - {{pool}}",
            "refId": "B"
          }
        ],
        "yaxes": [
          {
            "format": "short",
            "label": "連線數"
          }
        ]
      },
      {
        "id": 6,
        "title": "系統 CPU 使用率",
        "type": "graph",
        "gridPos": {
          "x": 0,
          "y": 16,
          "w": 8,
          "h": 8
        },
        "targets": [
          {
            "expr": "system_cpu_usage_percent",
            "legendFormat": "CPU 使用率",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "percent",
            "label": "使用率",
            "max": 100,
            "min": 0
          }
        ]
      },
      {
        "id": 7,
        "title": "系統記憶體使用",
        "type": "graph",
        "gridPos": {
          "x": 8,
          "y": 16,
          "w": 8,
          "h": 8
        },
        "targets": [
          {
            "expr": "system_memory_usage_bytes{type='used'}",
            "legendFormat": "已使用",
            "refId": "A"
          },
          {
            "expr": "system_memory_usage_bytes{type='available'}",
            "legendFormat": "可用",
            "refId": "B"
          }
        ],
        "yaxes": [
          {
            "format": "bytes",
            "label": "記憶體"
          }
        ]
      },
      {
        "id": 8,
        "title": "每秒日誌接收數",
        "type": "graph",
        "gridPos": {
          "x": 16,
          "y": 16,
          "w": 8,
          "h": 8
        },
        "targets": [
          {
            "expr": "sum(rate(logs_received_total[1m])) by (log_level)",
            "legendFormat": "{{log_level}}",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "short",
            "label": "日誌/秒"
          }
        ]
      },
      {
        "id": 9,
        "title": "Worker 處理效能",
        "type": "graph",
        "gridPos": {
          "x": 0,
          "y": 24,
          "w": 12,
          "h": 8
        },
        "targets": [
          {
            "expr": "rate(worker_processed_logs_total{status='success'}[1m])",
            "legendFormat": "Worker {{worker_id}} - 成功",
            "refId": "A"
          },
          {
            "expr": "rate(worker_processed_logs_total{status='failed'}[1m])",
            "legendFormat": "Worker {{worker_id}} - 失敗",
            "refId": "B"
          }
        ],
        "yaxes": [
          {
            "format": "short",
            "label": "處理速度"
          }
        ]
      },
      {
        "id": 10,
        "title": "資料庫查詢延遲",
        "type": "graph",
        "gridPos": {
          "x": 12,
          "y": 24,
          "w": 12,
          "h": 8
        },
        "targets": [
          {
            "expr": "histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket[5m])) by (le, query_type))",
            "legendFormat": "P95 - {{query_type}}",
            "refId": "A"
          },
          {
            "expr": "histogram_quantile(0.99, sum(rate(db_query_duration_seconds_bucket[5m])) by (le, query_type))",
            "legendFormat": "P99 - {{query_type}}",
            "refId": "B"
          }
        ],
        "yaxes": [
          {
            "format": "s",
            "label": "查詢時間"
          }
        ]
      }
    ]
  }
}
```

---

## 即時系統監控工具

### 1. htop - 互動式程序監控

#### 安裝與基本使用

```bash
# 安裝
sudo apt-get update
sudo apt-get install htop

# 啟動
htop

# 常用快捷鍵:
# F1: 說明
# F2: 設定
# F3: 搜尋程序
# F4: 過濾
# F5: 樹狀顯示
# F6: 排序
# F9: 終止程序
# F10: 離開
```

#### htop 配置文件

```bash
# ~/.config/htop/htoprc
fields=0 48 17 18 38 39 40 2 46 47 49 1
sort_key=46
sort_direction=1
hide_threads=0
hide_kernel_threads=1
hide_userland_threads=0
shadow_other_users=0
show_thread_names=0
show_program_path=1
highlight_base_name=1
highlight_megabytes=1
highlight_threads=1
tree_view=1
header_margin=1
detailed_cpu_time=0
cpu_count_from_zero=0
update_process_names=0
account_guest_in_cpu_meter=0
color_scheme=0
delay=15
left_meters=AllCPUs Memory Swap
left_meter_modes=1 1 1
right_meters=Tasks LoadAverage Uptime
right_meter_modes=2 2 2
```

### 2. glances - 全面的系統監控

#### 安裝

```bash
# Ubuntu/Debian
sudo apt-get install glances

# 或使用 pip
pip install glances[all]
```

#### 基本使用

```bash
# 基本啟動
glances

# Web 伺服器模式 (可透過瀏覽器存取)
glances -w

# 訪問: http://localhost:61208

# 客戶端模式 (連接到遠端伺服器)
glances -c <server_ip>

# 匯出到 CSV
glances --export csv --export-csv-file /tmp/glances.csv

# 匯出到 Prometheus
glances --export prometheus

# 常用快捷鍵:
# h: 說明
# q: 離開
# 1: 切換 CPU 顯示模式
# m: 按記憶體排序
# c: 按 CPU 排序
# i: 按 I/O 排序
# a: 自動排序
# d: 顯示/隱藏磁碟 I/O
# n: 顯示/隱藏網路
# s: 顯示/隱藏感應器
# f: 顯示/隱藏檔案系統
# /: 搜尋程序
```

#### glances 配置文件

```ini
# ~/.config/glances/glances.conf
[global]
check_update=false
refresh=2

[quicklook]
cpu_careful=50
cpu_warning=70
cpu_critical=90
mem_careful=50
mem_warning=70
mem_critical=90

[cpu]
user_careful=50
user_warning=70
user_critical=90
system_careful=50
system_warning=70
system_critical=90

[mem]
careful=50
warning=70
critical=90

[memswap]
careful=50
warning=70
critical=90

[load]
careful=0.7
warning=1.0
critical=5.0

[network]
hide=lo
rx_careful=70
rx_warning=80
rx_critical=90
tx_careful=70
tx_warning=80
tx_critical=90

[diskio]
hide=loop.*,ram.*
```

### 3. dstat - 即時系統統計

```bash
# 安裝
sudo apt-get install dstat

# 基本使用
dstat

# 詳細的 CPU、記憶體、網路、磁碟資訊
dstat -cdngy

# 每 5 秒更新一次,顯示 10 次
dstat 5 10

# 輸出到 CSV
dstat --output /tmp/dstat.csv 5
```

### 4. 客製化監控腳本

#### 系統資源監控腳本

```python
# system_monitor.py
#!/usr/bin/env python3
import psutil
import time
from datetime import datetime
import json

def get_system_info():
    """獲取系統資訊"""
    cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net_io = psutil.net_io_counters()
    
    return {
        'timestamp': datetime.now().isoformat(),
        'cpu': {
            'total': psutil.cpu_percent(interval=1),
            'per_core': cpu_percent,
            'count': psutil.cpu_count()
        },
        'memory': {
            'total': memory.total,
            'available': memory.available,
            'used': memory.used,
            'percent': memory.percent
        },
        'disk': {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': disk.percent
        },
        'network': {
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv
        }
    }

def format_bytes(bytes):
    """格式化位元組顯示"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0

def print_system_info():
    """漂亮地列印系統資訊"""
    info = get_system_info()
    
    print("\n" + "="*60)
    print(f"時間: {info['timestamp']}")
    print("="*60)
    
    print(f"\n🖥️  CPU:")
    print(f"  總使用率: {info['cpu']['total']:.1f}%")
    print(f"  每核心使用率: {', '.join([f'{x:.1f}%' for x in info['cpu']['per_core']])}")
    
    print(f"\n💾 記憶體:")
    print(f"  總量: {format_bytes(info['memory']['total'])}")
    print(f"  已使用: {format_bytes(info['memory']['used'])} ({info['memory']['percent']:.1f}%)")
    print(f"  可用: {format_bytes(info['memory']['available'])}")
    
    print(f"\n💿 磁碟:")
    print(f"  總量: {format_bytes(info['disk']['total'])}")
    print(f"  已使用: {format_bytes(info['disk']['used'])} ({info['disk']['percent']:.1f}%)")
    print(f"  可用: {format_bytes(info['disk']['free'])}")
    
    print(f"\n🌐 網路:")
    print(f"  發送: {format_bytes(info['network']['bytes_sent'])}")
    print(f"  接收: {format_bytes(info['network']['bytes_recv'])}")

def monitor_loop(interval=5, output_file=None):
    """持續監控並可選擇輸出到文件"""
    try:
        while True:
            print_system_info()
            
            if output_file:
                with open(output_file, 'a') as f:
                    info = get_system_info()
                    f.write(json.dumps(info) + '\n')
            
            time.sleep(interval)
    
    except KeyboardInterrupt:
        print("\n\n監控已停止")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='系統資源監控工具')
    parser.add_argument('-i', '--interval', type=int, default=5,
                       help='更新間隔(秒), 預設: 5')
    parser.add_argument('-o', '--output', type=str,
                       help='輸出文件路徑')
    
    args = parser.parse_args()
    
    print("🚀 開始系統監控...")
    print("按 Ctrl+C 停止")
    
    monitor_loop(interval=args.interval, output_file=args.output)
```

使用方式:
```bash
# 每 5 秒更新一次
python system_monitor.py

# 每 2 秒更新並儲存到文件
python system_monitor.py -i 2 -o system_metrics.jsonl
```

---

## 日誌分析工具

### 1. ELK Stack (Elasticsearch + Logstash + Kibana)

#### Docker Compose 配置

```yaml
version: '3.8'

services:
  elasticsearch:
    image: elasticsearch:8.11.0
    container_name: elasticsearch
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms1g -Xmx1g"
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
      - "9300:9300"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    networks:
      - elk
    restart: unless-stopped

  logstash:
    image: logstash:8.11.0
    container_name: logstash
    volumes:
      - ./logstash/config/logstash.yml:/usr/share/logstash/config/logstash.yml
      - ./logstash/pipeline:/usr/share/logstash/pipeline
    ports:
      - "5000:5000/tcp"
      - "5000:5000/udp"
      - "9600:9600"
    environment:
      LS_JAVA_OPTS: "-Xmx512m -Xms512m"
    networks:
      - elk
    depends_on:
      - elasticsearch
    restart: unless-stopped

  kibana:
    image: kibana:8.11.0
    container_name: kibana
    ports:
      - "5601:5601"
    environment:
      ELASTICSEARCH_URL: http://elasticsearch:9200
      ELASTICSEARCH_HOSTS: '["http://elasticsearch:9200"]'
    networks:
      - elk
    depends_on:
      - elasticsearch
    restart: unless-stopped

volumes:
  elasticsearch_data:

networks:
  elk:
    driver: bridge
```

#### Logstash 配置

```ruby
# logstash/pipeline/logstash.conf
input {
  # 從 FastAPI 接收日誌
  tcp {
    port => 5000
    codec => json
  }
  
  # 從文件讀取日誌
  file {
    path => "/var/log/app/*.log"
    start_position => "beginning"
    codec => json
  }
}

filter {
  # 解析時間戳
  date {
    match => [ "timestamp", "ISO8601" ]
    target => "@timestamp"
  }
  
  # 添加標籤
  if [log_level] == "ERROR" {
    mutate {
      add_tag => [ "error" ]
    }
  }
  
  # 解析 JSON 欄位
  if [log_data] {
    json {
      source => "log_data"
      target => "parsed_data"
    }
  }
  
  # Geo IP 查找 (如果有 IP 欄位)
  if [client_ip] {
    geoip {
      source => "client_ip"
    }
  }
}

output {
  # 輸出到 Elasticsearch
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "logs-%{+YYYY.MM.dd}"
  }
  
  # 除錯用: 輸出到標準輸出
  stdout {
    codec => rubydebug
  }
}
```

### 2. Grafana Loki

#### Docker Compose 配置

```yaml
version: '3.8'

services:
  loki:
    image: grafana/loki:latest
    container_name: loki
    ports:
      - "3100:3100"
    volumes:
      - ./loki/loki-config.yml:/etc/loki/loki-config.yml
      - loki_data:/loki
    command: -config.file=/etc/loki/loki-config.yml
    networks:
      - monitoring
    restart: unless-stopped

  promtail:
    image: grafana/promtail:latest
    container_name: promtail
    volumes:
      - ./promtail/promtail-config.yml:/etc/promtail/promtail-config.yml
      - /var/log:/var/log:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
    command: -config.file=/etc/promtail/promtail-config.yml
    networks:
      - monitoring
    depends_on:
      - loki
    restart: unless-stopped

volumes:
  loki_data:

networks:
  monitoring:
    driver: bridge
```

#### Loki 配置

```yaml
# loki/loki-config.yml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    address: 127.0.0.1
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
    final_sleep: 0s
  chunk_idle_period: 5m
  chunk_retain_period: 30s

schema_config:
  configs:
    - from: 2020-05-15
      store: boltdb
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 168h

storage_config:
  boltdb:
    directory: /loki/index
  filesystem:
    directory: /loki/chunks

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h

chunk_store_config:
  max_look_back_period: 0s

table_manager:
  retention_deletes_enabled: false
  retention_period: 0s
```

#### Promtail 配置

```yaml
# promtail/promtail-config.yml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  # 抓取 Docker 容器日誌
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        regex: '/(.*)'
        target_label: 'container'
      - source_labels: ['__meta_docker_container_log_stream']
        target_label: 'stream'
    
  # 抓取系統日誌
  - job_name: system
    static_configs:
      - targets:
          - localhost
        labels:
          job: varlogs
          __path__: /var/log/*.log
```

---

## 容器監控

### 1. Docker Stats

#### 基本使用

```bash
# 顯示所有容器的統計資訊
docker stats

# 顯示特定容器
docker stats fastapi-1 fastapi-2 fastapi-3

# 不持續顯示,只顯示一次
docker stats --no-stream

# 格式化輸出
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
```

#### 監控腳本

```bash
#!/bin/bash
# docker_monitor.sh

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🐳 Docker 容器監控"
echo "=================="
echo ""

# 獲取容器統計資訊
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}" | while read line; do
    # 跳過標題行
    if [[ $line == CONTAINER* ]]; then
        echo -e "${GREEN}$line${NC}"
        continue
    fi
    
    # 解析 CPU 使用率
    cpu=$(echo $line | awk '{print $2}' | sed 's/%//')
    
    # 根據 CPU 使用率著色
    if (( $(echo "$cpu > 80" | bc -l) )); then
        echo -e "${RED}$line${NC}"
    elif (( $(echo "$cpu > 50" | bc -l) )); then
        echo -e "${YELLOW}$line${NC}"
    else
        echo "$line"
    fi
done
```

### 2. cAdvisor (Container Advisor)

```yaml
# docker-compose.yml
cadvisor:
  image: gcr.io/cadvisor/cadvisor:latest
  container_name: cadvisor
  ports:
    - "8080:8080"
  volumes:
    - /:/rootfs:ro
    - /var/run:/var/run:ro
    - /sys:/sys:ro
    - /var/lib/docker/:/var/lib/docker:ro
    - /dev/disk/:/dev/disk:ro
  privileged: true
  devices:
    - /dev/kmsg
  networks:
    - monitoring
  restart: unless-stopped
```

訪問 cAdvisor UI: http://localhost:8080

---

## 完整監控架構

### 整合的 Docker Compose

```yaml
# complete-monitoring-stack.yml
version: '3.8'

services:
  # ==================== 應用服務 ====================
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    networks:
      - app
      - monitoring

  fastapi-1:
    build: .
    networks:
      - app
      - monitoring

  # ... 其他應用服務 ...

  # ==================== Prometheus 監控 ====================
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus:/etc/prometheus
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    networks:
      - monitoring

  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager:/etc/alertmanager
    networks:
      - monitoring

  # ==================== Exporters ====================
  redis-exporter:
    image: oliver006/redis_exporter:latest
    environment:
      - REDIS_ADDR=redis:6379
    networks:
      - monitoring

  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:latest
    environment:
      - DATA_SOURCE_NAME=postgresql://user:pass@postgres:5432/logs_db?sslmode=disable
    networks:
      - monitoring

  node-exporter:
    image: prom/node-exporter:latest
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    networks:
      - monitoring

  # ==================== 日誌收集 ====================
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    volumes:
      - ./loki:/etc/loki
      - loki_data:/loki
    networks:
      - monitoring

  promtail:
    image: grafana/promtail:latest
    volumes:
      - ./promtail:/etc/promtail
      - /var/log:/var/log:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
    networks:
      - monitoring

  # ==================== 容器監控 ====================
  cadvisor:
    image: gcr.io/cadvisor/cadvisor:latest
    ports:
      - "8080:8080"
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
    privileged: true
    networks:
      - monitoring

volumes:
  prometheus_data:
  grafana_data:
  loki_data:

networks:
  app:
    driver: bridge
  monitoring:
    driver: bridge
```

---

## 告警配置

### AlertManager 配置

```yaml
# alertmanager/alertmanager.yml
global:
  resolve_timeout: 5m
  
  # SMTP 配置 (Email 通知)
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@example.com'
  smtp_auth_username: 'alerts@example.com'
  smtp_auth_password: 'your_password'

# 路由配置
route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'
  
  routes:
    - match:
        severity: critical
      receiver: 'critical'
      continue: true
    
    - match:
        severity: warning
      receiver: 'warning'

# 接收器配置
receivers:
  - name: 'default'
    email_configs:
      - to: 'team@example.com'
        headers:
          Subject: '[監控告警] {{ .GroupLabels.alertname }}'
  
  - name: 'critical'
    email_configs:
      - to: 'oncall@example.com'
        headers:
          Subject: '[緊急告警] {{ .GroupLabels.alertname }}'
    
    # Slack 通知
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'
        channel: '#alerts-critical'
        title: '🚨 緊急告警'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
  
  - name: 'warning'
    email_configs:
      - to: 'team@example.com'
        headers:
          Subject: '[警告] {{ .GroupLabels.alertname }}'

# 抑制規則
inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'cluster', 'service']
```

### Prometheus 告警規則

```yaml
# prometheus/alerts/app_alerts.yml
groups:
  - name: app_alerts
    interval: 30s
    rules:
      # API 回應時間告警
      - alert: HighAPILatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API 回應時間過高"
          description: "P95 回應時間 {{ $value }}s 超過 500ms"
      
      # 錯誤率告警
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "錯誤率過高"
          description: "錯誤率 {{ $value | humanizePercentage }} 超過 5%"
      
      # Redis Stream 堆積告警
      - alert: RedisStreamBacklog
        expr: redis_stream_size > 50000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Redis Stream 訊息堆積"
          description: "Stream 大小 {{ $value }} 超過 50000"
      
      # 資料庫連線數告警
      - alert: HighDatabaseConnections
        expr: db_connections_active > 150
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "資料庫連線數過高"
          description: "活動連線數 {{ $value }} 超過 150"
      
      # 系統 CPU 告警
      - alert: HighCPUUsage
        expr: system_cpu_usage_percent > 80
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "系統 CPU 使用率過高"
          description: "CPU 使用率 {{ $value }}% 超過 80%"
      
      # 系統記憶體告警
      - alert: HighMemoryUsage
        expr: (system_memory_usage_bytes{type='used'} / system_memory_usage_bytes{type='total'}) * 100 > 85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "系統記憶體使用率過高"
          description: "記憶體使用率 {{ $value }}% 超過 85%"
      
      # 服務停機告警
      - alert: ServiceDown
        expr: up{job=~"fastapi|redis|postgres"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "服務停機"
          description: "{{ $labels.job }} 服務已停機"
```

### 快速啟動腳本

```bash
#!/bin/bash
# start_monitoring.sh

echo "🚀 啟動完整監控架構..."

# 創建必要的目錄
mkdir -p prometheus/alerts
mkdir -p grafana/provisioning/{datasources,dashboards}
mkdir -p alertmanager
mkdir -p loki
mkdir -p promtail

# 啟動所有服務
docker-compose -f complete-monitoring-stack.yml up -d

echo "✅ 監控服務已啟動"
echo ""
echo "📊 訪問以下 URL:"
echo "  - Prometheus: http://localhost:9090"
echo "  - Grafana: http://localhost:3000 (admin/admin123)"
echo "  - AlertManager: http://localhost:9093"
echo "  - cAdvisor: http://localhost:8080"
echo ""
echo "🔍 查看服務狀態:"
docker-compose -f complete-monitoring-stack.yml ps
```

---

## 總結

這個完整的監控方案提供了:

✅ **多層次監控**
- 應用層指標 (HTTP 請求、業務邏輯)
- 系統層指標 (CPU、記憶體、磁碟)
- 容器層指標 (Docker 容器資源)
- 服務層指標 (Redis、PostgreSQL、Nginx)

✅ **即時可視化**
- Grafana 儀表板
- Prometheus 查詢介面
- cAdvisor 容器監控

✅ **智能告警**
- 多級別告警 (Critical、Warning)
- 多通道通知 (Email、Slack)
- 告警抑制和分組

✅ **日誌分析**
- ELK Stack 或 Loki
- 集中式日誌收集
- 強大的搜尋和分析能力

這套監控系統可以幫助你全面掌握系統狀態,快速發現和解決問題! 🎯