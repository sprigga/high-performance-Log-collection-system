# Nginx 與 FastAPI 配置指南
  
## 目錄
- [架構概述](#架構概述 )
- [Nginx 配置詳解](#nginx-配置詳解 )
- [負載均衡機制](#負載均衡機制 )
- [API 端點映射](#api-端點映射 )
- [FastAPI 應用設置](#fastapi-應用設置 )
- [FastAPI 詳細配置與實作](#fastapi-詳細配置與實作 )
- [Redis 完整配置與架構](#redis-完整配置與架構 )
  - [Redis 伺服器配置](#1-redis-伺服器配置 )
  - [Redis 持久化策略](#2-redis-持久化策略-aof )
  - [Redis 記憶體管理策略](#3-redis-記憶體管理策略 )
  - [Redis 連線池配置](#4-redis-連線池配置 )
  - [Redis Stream 詳細機制](#5-redis-stream-詳細機制 )
  - [Redis 快取層詳解](#6-redis-快取層詳解 )
  - [Redis 雙重角色](#7-redis-雙重角色stream-vs-cache )
  - [Redis 與 PostgreSQL 協作模式](#8-redis-與-postgresql-協作模式 )
- [Worker 工作流程](#worker-工作流程 )
- [Worker 詳細實作](#worker-詳細實作 )
- [Worker 完整生命週期](#worker-完整生命週期 )
- [FastAPI 與 Worker 協作機制](#fastapi-與-worker-協作機制 )
- [請求處理流程](#請求處理流程 )
- [批量處理與效能優化](#批量處理與效能優化 )
- [性能優化配置](#性能優化配置 )
- [健康檢查與監控](#健康檢查與監控 )
- [擴展與維護](#擴展與維護 )
- [總結](#總結 )
  
## 架構概述
  
本日誌收集系統採用 Nginx 作為反向代理和負載均衡器，後端部署多個 FastAPI 實例來處理日誌收集請求，並使用獨立的 Worker 服務將日誌非同步處理並持久化到 PostgreSQL 數據庫。整體架構如下：
  
```
外部請求 → Nginx (負載均衡) → FastAPI 實例 1 → Redis (隊列) → Worker → PostgreSQL
                            → FastAPI 實例 2                        → PostgreSQL
                            → ... (更多實例)
```
  
以下是系統架構的詳細圖示：
  
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client        │    │    Nginx        │    │  Redis (Queue)  │
│   Requests      │◄──►│   (Reverse      │◄──►│                 │
└─────────────────┘    │   Proxy)        │    │                 │
                       │                 │    └─────────────────┘
                       └─────────────────┘              │
                              │                         │
                    ┌─────────┼─────────┐               │
                    │         │         │               ▼
             ┌─────────────┐  │  ┌─────────────┐    ┌─────────────┐
             │  FastAPI    │  │  │  FastAPI    │    │   Worker    │
             │  Instance 1 │  │  │  Instance 2 │    │             │
             └─────────────┘  │  └─────────────┘    └─────────────┘
                              │                           │
                    ┌─────────────────┐                   │
                    │ Storage Layer   │                   │
                    │  ┌────────────┐ │                   │
                    │  │ PostgreSQL │ │◄──────────────────┘
                    │  └────────────┘ │
                    └─────────────────┘
```
  
## Nginx 配置詳解
  
### 1. 基本配置
  
```nginx
events {
    worker_connections 4096;    # 提升以支援更高並發
}
```
  
- `worker_connections`: 設定每個 worker 進程可處理的最大連線數，從默認的 1024 提升至 4096 以支援高併發請求。
  
### 2. 上游服務配置 (Upstream)
  
```nginx
upstream fastapi_backend {
    least_conn;  # 最少連線數演算法（適合長連線）
  
    server fastapi-1:8000 weight=1 max_fails=3 fail_timeout=30s;
    server fastapi-2:8000 weight=1 max_fails=3 fail_timeout=30s;
  
    keepalive 128;  # 提升連線池以支援更高並發
}
```
  
- `least_conn`: 使用最少連線數算法，適合長連線場景
- `server`: 定義後端 FastAPI 服務地址和端口
- `weight`: 服務器權重（默認為 1）
- `max_fails` 和 `fail_timeout`: 容錯配置
- `keepalive`: HTTP 連線池大小，提升連線複用效率
  
### 3. 日誌格式配置
  
```nginx
log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                '$status $body_bytes_sent "$http_referer" '
                '"$http_user_agent" upstream: $upstream_addr '
                'response_time: $upstream_response_time';
```
  
- 記錄詳細的請求資訊，包括上游服務器地址和響應時間，便於性能分析和問題排查。
  
### 4. 限流配置
  
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10000r/s;
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;
```
  
- `rate=10000r/s`: 每秒最多處理 10,000 個請求（為壓力測試調高）
- `zone=conn_limit`: 限制單個 IP 的連線數
  
## 負載均衡機制
  
### 核心配置解析
  
本系統的負載均衡核心配置位於 `nginx/nginx.conf` 的 upstream 區塊：
  
```nginx
upstream fastapi_backend {
    least_conn;  # 負載均衡演算法
  
    server fastapi-1:8000 weight=1 max_fails=3 fail_timeout=30s;
    server fastapi-2:8000 weight=1 max_fails=3 fail_timeout=30s;
  
    keepalive 128;  # 連線池大小
}
```
  
### 負載均衡演算法詳解
  
#### 1. Least Connections (最少連線數) 演算法
  
Nginx 使用 `least_conn` 指令實現最少連線數演算法：
  
**工作原理：**
```
請求到達 → 檢查所有後端服務器的活躍連線數 → 選擇連線數最少的服務器 → 轉發請求
```
  
**具體流程：**
1. 當新請求到達時，Nginx 檢查 upstream 池中所有服務器
2. 計算每個服務器的當前活躍連線數（考慮權重）
3. 選擇 `active_connections / weight` 值最小的服務器
4. 將請求轉發到該服務器
  
**為何選擇此演算法：**
- 適合**長連線場景**：日誌系統可能有持久連線
- **動態負載分配**：根據實際負載而非固定順序分配
- **避免不均勻分佈**：防止某個實例過載而其他閒置
  
**與其他演算法比較：**
| 演算法 | 特點 | 適用場景 |
|--------|------|----------|
| `round_robin` (默認) | 輪詢分配 | 請求處理時間相近 |
| `least_conn` | 最少連線優先 | 請求處理時間差異大、長連線 |
| `ip_hash` | 同一 IP 固定後端 | 需要會話保持 |
| `random` | 隨機選擇 | 均衡分佈 |
  
#### 2. 權重配置 (Weight)
  
```nginx
server fastapi-1:8000 weight=1;
server fastapi-2:8000 weight=1;
```
  
- 當前配置：兩個實例權重相同（1:1）
- **計算方式**：實際負載 = 連線數 / 權重
- **擴展示例**：若設置 `weight=2`，該服務器將承擔雙倍流量
  
### 請求分發流程
  
```
┌─────────────┐
│ 客戶端請求   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│              Nginx 負載均衡器                 │
│  ┌─────────────────────────────────────┐    │
│  │        1. 接收請求                    │    │
│  │           ↓                          │    │
│  │        2. 路由匹配                    │    │
│  │        (location /api/log)           │    │
│  │           ↓                          │    │
│  │        3. 限流檢查                    │    │
│  │        (rate=10000r/s)               │    │
│  │           ↓                          │    │
│  │        4. 連線數計算                   │    │
│  │        fastapi-1: 45 連線            │    │
│  │        fastapi-2: 38 連線 ✓           │    │
│  │           ↓                          │    │
│  │        5. 選擇最少連線服務器            │    │
│  │        (fastapi-2)                   │    │
│  │           ↓                          │    │
│  │        6. 轉發請求                    │    │
│  │        proxy_pass → fastapi-2:8000   │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
       │
       ▼
┌──────┴──────┐
│  FastAPI-2   │
└─────────────┘
```
  
### 容錯與故障轉移機制
  
```nginx
server fastapi-1:8000 weight=1 max_fails=3 fail_timeout=30s;
```
  
**參數解析：**
- **`max_fails=3`**: 在 fail_timeout 時間內允許的最大失敗次數
- **`fail_timeout=30s`**:
  - 統計失敗次數的時間窗口（30 秒）
  - 服務器被標記為不可用後的恢復等待時間
  
**故障檢測流程：**
```
時間線：T=0s
├─ 請求 1 → fastapi-1 → 失敗 (fail_count=1)
├─ 請求 2 → fastapi-1 → 失敗 (fail_count=2)
├─ 請求 3 → fastapi-1 → 失敗 (fail_count=3)
│
├─ T=0.5s: fastapi-1 標記為 DOWN
│  (30 秒內失敗 3 次)
│
├─ T=0.5s ~ T=30.5s:
│  所有請求轉發至 fastapi-2
│
├─ T=30.5s: fastapi-1 恢復為 UP
│  重新加入負載均衡池
│
└─ 繼續監控...
```
  
**自動恢復：**
- 30 秒後 Nginx 自動嘗試將故障服務器重新加入池中
- 如果服務器已恢復，則正常接收流量
- 如果仍然故障，重新開始故障計數
  
### 連線池與持久連線
  
```nginx
upstream fastapi_backend {
    ...
    keepalive 128;
}
  
location /api/log {
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    ...
}
```
  
**連線池工作原理：**
  
```
不使用連線池：
Client → Nginx → [建立 TCP 連線] → FastAPI → [關閉連線]
Client → Nginx → [建立 TCP 連線] → FastAPI → [關閉連線]
(每次請求都建立新連線，開銷大)
  
使用連線池 (keepalive 128)：
Client → Nginx → [復用現有連線] → FastAPI
                 ↑ 連線池 (最多 128 個空閒連線)
Client → Nginx → [復用現有連線] → FastAPI
(連線重用，減少 TCP 握手開銷)
```
  
**關鍵配置說明：**
  
1. **`keepalive 128`**:
   - 每個 worker 進程維護最多 128 個空閒連線
   - 超過此數量的空閒連線將被關閉
   - 有效減少連線建立開銷
  
2. **`proxy_http_version 1.1`**:
   - 使用 HTTP/1.1 協議（支援持久連線）
   - 默認的 HTTP/1.0 不支援 keepalive
  
3. **`proxy_set_header Connection ""`**:
   - 清除客戶端的 Connection 頭
   - 防止客戶端的 `Connection: close` 關閉後端連線
   - 確保 Nginx 到後端的連線保持活躍
  
**性能影響：**
- 減少 TCP 三次握手延遲（約 1-2ms/請求）
- 降低系統資源消耗（減少 TIME_WAIT 狀態連線）
- 提升高併發場景下的吞吐量
  
### 負載均衡狀態監控
  
通過日誌格式追蹤負載分佈：
  
```nginx
log_format main '... upstream: $upstream_addr response_time: $upstream_response_time';
```
  
**監控指標：**
- `<img src="https://latex.codecogs.com/gif.latex?upstream_addr`:%20記錄實際處理請求的後端服務器-%20`"/>upstream_response_time`: 後端響應時間
  
**分析示例：**
```bash
# 查看負載分佈
grep "upstream:" /var/log/nginx/access.log | awk '{print $NF}' | sort | uniq -c
  
# 輸出示例：
#   5023 fastapi-1:8000
#   4977 fastapi-2:8000
# (接近 1:1 分佈，表示負載均衡正常)
```
  
### 動態擴展後端服務器
  
**添加新實例步驟：**
  
1. **更新 docker-compose.yml**:
```yaml
fastapi-3:
  build:
    context: ./app
    dockerfile: Dockerfile
  container_name: log-fastapi-3
  command: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 6
  environment:
    - INSTANCE_NAME=fastapi-3
    ...
```
  
2. **更新 nginx.conf**:
```nginx
upstream fastapi_backend {
    least_conn;
    server fastapi-1:8000 weight=1 max_fails=3 fail_timeout=30s;
    server fastapi-2:8000 weight=1 max_fails=3 fail_timeout=30s;
    server fastapi-3:8000 weight=1 max_fails=3 fail_timeout=30s;  # 新增
    keepalive 128;
}
```
  
3. **重新載入配置**:
```bash
docker-compose up -d fastapi-3
docker-compose exec nginx nginx -s reload
```
  
**優點：**
- 無需重啟整個服務
- 零停機時間擴展
- 新實例自動加入負載均衡池
  
## API 端點映射
  
### 日誌寫入端點
  
```nginx
location /api/log {
    limit_req zone=api_limit burst=20000 nodelay;
    limit_conn conn_limit 1000;
  
    proxy_pass http://fastapi_backend;
    proxy_http_version 1.1;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```
  
- **功能**: 接收單個日誌條目
- **限流**: 每秒 10,000 請求，突發 20,000
- **超時**: 連線 5s，發送/讀取各 10s
  
### 批量日誌端點
  
```nginx
location /api/logs/batch {
    limit_req zone=api_limit burst=20000 nodelay;
    limit_conn conn_limit 1000;
  
    proxy_pass http://fastapi_backend;
    client_max_body_size 50M;  # 支援較大請求體
}
```
  
- **功能**: 批量接收日誌條目
- **載體限制**: 50MB（比普通端點更大）
- **超時**: 更長的讀寫超時（30s）
  
### 查詢端點
  
```nginx
location /api/logs {
    limit_req zone=api_limit burst=200 nodelay;
    proxy_pass http://fastapi_backend;
    proxy_read_timeout 30s;  # 較長的讀取超時
}
```
  
- **功能**: 查詢日誌資料
- **限流**: 較保守（burst=200），避免查詢對系統造成過大壓力
- **超時**: 30s，允許複雜查詢
  
### 統計端點
  
```nginx
location /api/stats {
    limit_req zone=api_limit burst=200 nodelay;
    proxy_pass http://fastapi_backend;
    proxy_read_timeout 30s;
}
```
  
- **功能**: 獲取系統統計資訊
- **快取**: FastAPI 內部使用 Redis 快取結果
  
### 文件端點
  
```nginx
location /docs {
    proxy_pass http://fastapi_backend/docs;
}
location /openapi.json {
    proxy_pass http://fastapi_backend/openapi.json;
}
location /redoc {
    proxy_pass http://fastapi_backend/redoc;
}
```
  
- **功能**: 提供 FastAPI 自動生成的 API 文件
  
## FastAPI 應用設置
  
### Docker Compose 配置
  
```yaml
fastapi-1:
  build:
    context: ./app
    dockerfile: Dockerfile
  command: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 6  # 提升 workers 數量
  environment:
    - POSTGRES_HOST=postgres
    - POSTGRES_PORT=5432
    - POSTGRES_USER=loguser
    - POSTGRES_PASSWORD=logpass
    - POSTGRES_DB=logsdb
    - REDIS_HOST=redis
    - REDIS_PORT=6379
    - INSTANCE_NAME=fastapi-1
```
  
- `--workers 6`: 啟動 6 個工作進程以處理更多併發請求
- `INSTANCE_NAME`: 用於區分不同實例的環境變量
- 服務容器名稱為 `fastapi-1` 和 `fastapi-2`，對應 nginx upstream 中的服務器定義
  
### FastAPI 應用特性
  
- 支援 async/await 非同步處理
- 使用 Redis 作為日誌隊列和快取層
- 使用 PostgreSQL 作為持久化存儲
- 實現了健康檢查端點 `/health`
- 提供 Redis 連線池配置以支援高併發
  
## FastAPI 詳細配置與實作
  
### 1. 應用程式初始化
  
**檔案位置**: `app/main.py` (第 24-28 行)
  
```python
app = FastAPI(
    title="高效能日誌收集系統",
    description="基於 FastAPI + Redis + PostgreSQL 的日誌收集系統",
    version="1.0.0"
)
```
  
**應用程式啟動事件** (第 43-88 行):
  
```python
@app.on_event("startup")
async def startup_event():
    global redis_client
  
    print(f"🚀 Starting FastAPI instance: {INSTANCE_NAME}")
  
    # 建立 Redis 連線池
    pool = redis.ConnectionPool(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        max_connections=200  # 提升至 200 以支援高併發
    )
    redis_client = redis.Redis(connection_pool=pool)
  
    # 測試 Redis 連線
    await redis_client.ping()
    print("✅ Redis connection successful")
  
    # 測試 PostgreSQL 連線
    if await test_db_connection():
        print("✅ PostgreSQL connection successful")
  
    # 確保 Redis Stream 消費者群組存在
    try:
        await redis_client.xgroup_create(
            name='logs:stream',
            groupname='log_workers',
            id='0',
            mkstream=True
        )
        print("✅ Redis Stream group created")
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            print("ℹ️ Redis Stream group already exists")
```
  
**關鍵初始化步驟**:
1. 建立 Redis 連線池（最大 200 連線）
2. 驗證 Redis 和 PostgreSQL 連線狀態
3. 創建 Redis Stream 消費者群組（若不存在）
  
### 2. Redis 連線配置
  
**檔案位置**: `app/main.py` (第 33-60 行)
  
```python
# 環境變數配置
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
INSTANCE_NAME = os.getenv('INSTANCE_NAME', 'fastapi-default')
  
# 連線池設置
pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,    # 自動解碼響應為字串
    max_connections=200       # 最大連線數（從 50 提升至 200）
)
redis_client = redis.Redis(connection_pool=pool)
```
  
**連線池參數說明**:
| 參數 | 值 | 說明 |
|------|-----|------|
| `max_connections` | 200 | 支援高併發請求 |
| `decode_responses` | True | 自動將 bytes 轉為 str |
| `socket_timeout` | 預設 | 連線超時控制 |
  
### 3. 資料庫連線配置
  
**檔案位置**: `app/database.py` (第 13-66 行)
  
#### PostgreSQL 連線參數
  
```python
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'loguser')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'logpass')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'logsdb')
  
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
ASYNC_DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
```
  
#### 非同步引擎（FastAPI 使用）
  
```python
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=10,           # 常駐連線數
    max_overflow=5,         # 額外連線數（總計可達 15）
    pool_timeout=30,        # 連線等待超時（秒）
    pool_recycle=3600,      # 連線回收時間（1 小時）
    pool_pre_ping=True,     # 使用前測試連線
    echo=False              # 生產模式（不輸出 SQL）
)
```
  
#### 同步引擎（Worker 使用）
  
```python
sync_engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    echo=False
)
```
  
**連線池配置要點**:
- **Pool Size**: 10 個常駐連線
- **Max Overflow**: 5 個額外連線（總計 15）
- **Pool Recycle**: 3600 秒後回收連線（避免過期連線）
- **Pre-ping**: 每次使用前測試連線有效性
  
### 4. API 端點詳細實作
  
#### 4.1 單一日誌寫入端點
  
**檔案位置**: `app/main.py` (第 147-185 行)
  
```python
@app.post("/api/log", response_model=LogEntryResponse)
async def create_log(log: LogEntryRequest):
    """
    接收單一日誌條目並寫入 Redis Stream
  
    處理流程:
    1. 驗證日誌格式（Pydantic 自動完成）
    2. 構建日誌字典
    3. 寫入 Redis Stream（使用 XADD）
    4. 立即返回響應（非同步處理）
  
    預期響應時間: < 5ms
    """
    try:
        log_dict = {
            "device_id": log.device_id,
            "log_level": log.log_level,
            "message": log.message,
            "log_data": json.dumps(log.log_data) if log.log_data else "{}",
            "timestamp": datetime.now().isoformat()
        }
  
        # 寫入 Redis Stream
        message_id = await redis_client.xadd(
            name="logs:stream",        # Stream 名稱
            fields=log_dict,           # 訊息內容
            maxlen=100000,             # 保留最近 10 萬筆
            approximate=True           # 使用近似裁剪提升效能
        )
  
        return LogEntryResponse(
            status="received",
            message_id=str(message_id),
            received_at=datetime.now()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```
  
**Redis XADD 命令說明**:
- **name**: Stream 的鍵名 (`logs:stream`)
- **fields**: 訊息的鍵值對資料
- **maxlen**: 限制 Stream 長度為 100,000 筆
- **approximate**: 使用近似裁剪（效能優化，實際長度可能略超過 maxlen）
  
#### 4.2 批量日誌寫入端點
  
**檔案位置**: `app/main.py` (第 190-237 行)
  
```python
@app.post("/api/logs/batch", response_model=BatchLogEntryResponse)
async def create_batch_logs(batch: BatchLogEntryRequest):
    """
    批量接收日誌條目並使用 Redis Pipeline 批次寫入
  
    處理流程:
    1. 驗證批量格式（最多 1000 筆）
    2. 建立 Redis Pipeline
    3. 批次執行 XADD 命令
    4. 返回所有 message_id
  
    預期吞吐量: 10,000+ logs/秒
    """
    try:
        current_time = datetime.now().isoformat()
  
        # 使用 Pipeline 減少網路往返
        pipe = redis_client.pipeline()
  
        for log in batch.logs:
            log_dict = {
                "device_id": log.device_id,
                "log_level": log.log_level,
                "message": log.message,
                "log_data": json.dumps(log.log_data) if log.log_data else "{}",
                "timestamp": current_time
            }
            pipe.xadd(
                name="logs:stream",
                fields=log_dict,
                maxlen=100000,
                approximate=True
            )
  
        # 批次執行所有命令
        results = await pipe.execute()
        message_ids = [str(r) for r in results]
  
        return BatchLogEntryResponse(
            status="received",
            count=len(message_ids),
            message_ids=message_ids,
            received_at=datetime.now()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```
  
**Pipeline 批次處理優勢**:
- **減少網路延遲**: 一次往返執行多個命令
- **原子性**: 所有命令在伺服器端連續執行
- **高吞吐量**: 支援每批次最多 1000 筆日誌
  
#### 4.3 日誌查詢端點（帶快取）
  
**檔案位置**: `app/main.py` (第 242-318 行)
  
```python
@app.get("/api/logs/{device_id}", response_model=BatchLogQueryResponse)
async def get_logs(
    device_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查詢特定設備的日誌資料（支援快取）
  
    處理流程:
    1. 檢查 Redis 快取
    2. 快取命中 → 直接返回
    3. 快取未命中 → 查詢 PostgreSQL
    4. 將結果寫入快取（TTL 5 分鐘）
    """
    cache_key = f"cache:logs:{device_id}:{limit}"
  
    # 嘗試從快取獲取
    try:
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            logs_data = json.loads(cached_data)
            return BatchLogQueryResponse(
                total=len(logs_data),
                source="cache",
                data=logs_data
            )
    except Exception as e:
        print(f"Cache read error: {e}")
  
    # 快取未命中，查詢資料庫
    query = select(Log).where(
        Log.device_id == device_id
    ).order_by(
        Log.created_at.desc()
    ).limit(limit)
  
    result = await db.execute(query)
    logs = result.scalars().all()
  
    logs_data = [
        {
            "id": log.id,
            "device_id": log.device_id,
            "log_level": log.log_level,
            "message": log.message,
            "log_data": log.log_data,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
  
    # 寫入快取（TTL 5 分鐘）
    try:
        await redis_client.setex(
            name=cache_key,
            time=300,  # 5 分鐘
            value=json.dumps(logs_data, default=str)
        )
    except Exception as e:
        print(f"Cache write error: {e}")
  
    return BatchLogQueryResponse(
        total=len(logs_data),
        source="database",
        data=logs_data
    )
```
  
**快取策略**:
- **快取鍵格式**: `cache:logs:{device_id}:{limit}`
- **TTL**: 300 秒（5 分鐘）
- **快取穿透保護**: 即使資料庫為空也快取結果
  
#### 4.4 統計資訊端點
  
**檔案位置**: `app/main.py` (第 323-394 行)
  
```python
@app.get("/api/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_async_db)):
    """
    獲取系統統計資訊（快取 60 秒）
  
    返回:
    - 總日誌數量
    - 按級別分類的日誌數
    - 最近活躍的設備（前 10 名）
    """
    cache_key = "cache:stats"
  
    # 檢查快取
    cached_stats = await redis_client.get(cache_key)
    if cached_stats:
        return json.loads(cached_stats)
  
    # 總日誌數
    total_result = await db.execute(select(func.count(Log.id)))
    total_logs = total_result.scalar()
  
    # 按級別分類
    level_query = select(
        Log.log_level,
        func.count(Log.id)
    ).group_by(Log.log_level)
    level_result = await db.execute(level_query)
    logs_by_level = {row[0]: row[1] for row in level_result.all()}
  
    # 最近活躍設備
    device_query = select(
        Log.device_id,
        func.count(Log.id)
    ).group_by(Log.device_id).order_by(
        func.count(Log.id).desc()
    ).limit(10)
    device_result = await db.execute(device_query)
    recent_devices = [row[0] for row in device_result.all()]
  
    stats = StatsResponse(
        total_logs=total_logs,
        logs_by_level=logs_by_level,
        recent_devices=recent_devices
    )
  
    # 快取 60 秒
    await redis_client.setex(
        cache_key,
        60,
        json.dumps(stats.dict(), default=str)
    )
  
    return stats
```
  
### 5. 資料模型定義
  
**檔案位置**: `app/models.py`
  
#### ORM 模型（資料庫映射）
  
```python
class Log(Base):
    __tablename__ = 'logs'
  
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(50), nullable=False, index=True)
    log_level = Column(String(20), nullable=False, index=True)
    message = Column(Text, nullable=True)
    log_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    indexed_at = Column(DateTime(timezone=True), server_default=func.now())
  
    __table_args__ = (
        Index('idx_device_created', 'device_id', 'created_at'),
        Index('idx_created_desc', 'created_at'),
    )
```
  
#### Pydantic 請求模型
  
```python
class LogEntryRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=50, description="設備 ID")
    log_level: str = Field(..., description="日誌級別: DEBUG/INFO/WARNING/ERROR/CRITICAL")
    message: str = Field(..., min_length=1, max_length=5000, description="日誌訊息")
    log_data: Optional[Dict[str, Any]] = Field(default={}, description="額外資料")
  
class BatchLogEntryRequest(BaseModel):
    logs: list[LogEntryRequest] = Field(..., min_length=1, max_length=1000)
```
  
#### Pydantic 響應模型
  
```python
class LogEntryResponse(BaseModel):
    status: str
    message_id: str
    received_at: datetime
  
class BatchLogEntryResponse(BaseModel):
    status: str
    count: int
    message_ids: list[str]
    received_at: datetime
  
class BatchLogQueryResponse(BaseModel):
    total: int
    source: str  # "cache" 或 "database"
    data: list[Dict[str, Any]]
```
  
### 6. 資料庫結構設計
  
**檔案位置**: `postgres/init.sql`
  
#### 主表結構
  
```sql
CREATE TABLE IF NOT EXISTS logs (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL,
    log_level VARCHAR(20) NOT NULL,
    message TEXT,
    log_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    indexed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```
  
#### 索引優化策略
  
```sql
-- 複合索引：最常用的查詢模式（設備 ID + 時間降序）
CREATE INDEX IF NOT EXISTS idx_device_created
ON logs(device_id, created_at DESC);
  
-- 日誌級別索引：支援按級別過濾
CREATE INDEX IF NOT EXISTS idx_log_level
ON logs(log_level);
  
-- 時間索引：支援時間範圍查詢
CREATE INDEX IF NOT EXISTS idx_created_at
ON logs(created_at DESC);
  
-- GIN 索引：支援 JSONB 欄位查詢
CREATE INDEX IF NOT EXISTS idx_log_data_gin
ON logs USING GIN(log_data);
```
  
**索引設計考量**:
- **idx_device_created**: 覆蓋 90% 的查詢模式
- **idx_log_level**: 支援按級別統計
- **idx_created_at**: 支援時序查詢
- **idx_log_data_gin**: 支援 JSON 內容搜尋
  
## Redis 完整配置與架構
  
Redis 在本系統中扮演多重角色：**訊息佇列（Stream）**、**資料快取（Cache）** 和 **緩衝層（Buffer）**。以下是 Redis 的完整配置與運作機制。
  
### 1. Redis 伺服器配置
  
**檔案位置**: `docker-compose.yml` (第 98-119 行)
  
```yaml
redis:
  image: redis:7-alpine
  container_name: log-redis
  ports:
    - "16891:6379"              # 冷門端口避免衝突
  volumes:
    - redis-data:/data          # 資料持久化
  command: >
    redis-server
    --appendonly yes            # 啟用 AOF 持久化
    --maxmemory 512mb           # 記憶體上限
    --maxmemory-policy allkeys-lru  # LRU 淘汰策略
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 3s
    retries: 3
```
  
#### 關鍵配置參數解析
  
| 參數 | 值 | 說明 |
|------|-----|------|
| **image** | `redis:7-alpine` | 輕量化 Alpine 版本，體積小、效能佳 |
| **--appendonly yes** | AOF 持久化 | 每次寫入操作都追加到檔案，資料安全性高 |
| **--maxmemory 512mb** | 512MB | Redis 最大使用記憶體上限 |
| **--maxmemory-policy** | `allkeys-lru` | 當記憶體滿時，淘汰最近最少使用的 key |
  
### 2. Redis 持久化策略 (AOF)
  
```
┌─────────────────────────────────────────────────────────────┐
│                    AOF 持久化工作流程                         │
└─────────────────────────────────────────────────────────────┘
  
Redis 寫入命令
       │
       ▼
┌─────────────────┐
│  寫入 AOF 緩衝區  │
└─────────────────┘
       │
       ▼ (根據 fsync 策略)
┌─────────────────┐
│  同步到磁碟      │  appendonly.aof
└─────────────────┘
       │
       ▼ (伺服器重啟時)
┌─────────────────┐
│  重建記憶體資料   │
└─────────────────┘
```
  
**AOF 優勢**：
- **資料安全性高**：每個寫入命令都會被記錄
- **可讀性佳**：AOF 檔案是純文字格式，便於除錯
- **適合 Stream**：Redis Stream 的資料不會因重啟而遺失
  
**AOF 配置選項**：
- `appendfsync always`: 每次寫入都同步（最安全，效能最低）
- `appendfsync everysec`: 每秒同步一次（預設，平衡安全與效能）
- `appendfsync no`: 由作業系統決定（效能最佳，風險較高）
  
### 3. Redis 記憶體管理策略
  
**記憶體使用分佈**：
  
```
┌─────────────────────────────────────────────────────────────┐
│                  Redis 512MB 記憶體配置                       │
└─────────────────────────────────────────────────────────────┘
  
├── Redis Stream (logs:stream)
│   ├─ maxlen: 100,000 筆日誌
│   └─ 預估大小: ~200-400MB (每筆約 2-4KB)
│
├── 快取資料
│   ├─ cache:logs:{device_id}:{limit}  (TTL: 300s)
│   ├─ cache:stats                      (TTL: 60s)
│   └─ 預估大小: ~50-100MB
│
└── 系統開銷與緩衝
    └─ ~50MB
```
  
**LRU (Least Recently Used) 淘汰策略**：
  
```python
# 當記憶體達到 512MB 上限時
if memory_used >= 512MB:
    # 找出所有 key 中最久未使用的
    least_recently_used_key = find_lru_key(all_keys)
    # 淘汰該 key
    delete(least_recently_used_key)
```
  
**淘汰策略比較**：
  
| 策略 | 說明 | 適用場景 |
|------|------|----------|
| `allkeys-lru` ✓ | 所有 key 中淘汰 LRU | 混合用途（快取+佇列）|
| `volatile-lru` | 僅有 TTL 的 key 中淘汰 | 純快取場景 |
| `noeviction` | 不淘汰，滿時報錯 | 資料不可遺失場景 |
| `allkeys-random` | 隨機淘汰 | 訪問模式均勻 |
  
### 4. Redis 連線池配置
  
#### 4.1 FastAPI 非同步連線池
  
**檔案位置**: `app/main.py` (第 53-60 行)
  
```python
# FastAPI 啟動時初始化
pool = redis.ConnectionPool(
    host=REDIS_HOST,              # 從環境變數讀取 (預設: redis)
    port=REDIS_PORT,              # 從環境變數讀取 (預設: 6379)
    decode_responses=True,        # 自動解碼為字串
    max_connections=200           # 最大連線數 (提升至 200)
)
redis_client = redis.Redis(connection_pool=pool)
```
  
**連線池參數說明**：
  
| 參數 | 值 | 說明 |
|------|-----|------|
| `max_connections` | 200 | 支援高併發（6 workers × ~33 連線/worker）|
| `decode_responses` | True | 自動將 bytes 轉為 str |
| `socket_timeout` | 預設 | 讀寫超時控制 |
| `retry_on_timeout` | 預設 False | 超時是否重試 |
  
**連線池工作原理**：
  
```
┌─────────────────────────────────────────────────────────────┐
│                   連線池管理流程                              │
└─────────────────────────────────────────────────────────────┘
  
FastAPI Worker 1 ─┐
FastAPI Worker 2 ─┤    ┌────────────────────┐
FastAPI Worker 3 ─┼───►│   連線池            │
FastAPI Worker 4 ─┤    │  (max_conn=200)    │
FastAPI Worker 5 ─┤    │                    │
FastAPI Worker 6 ─┘    │  ┌──┬──┬──┬──┐    │     ┌─────────┐
                       │  │C1│C2│C3│..│    │────►│  Redis  │
                       │  └──┴──┴──┴──┘    │     │  Server │
                       └────────────────────┘     └─────────┘
  
流程：
1. 請求到達 → 從連線池借用連線
2. 執行 Redis 命令
3. 命令完成 → 連線歸還連線池
4. 連線複用，減少建立開銷
```
  
#### 4.2 Worker 同步連線池
  
**檔案位置**: `app/worker.py` (第 54-61 行)
  
```python
# Worker 啟動時初始化
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=5,      # 連線超時 5 秒
    socket_keepalive=True,         # 保持連線存活
    max_connections=10             # Worker 使用較少連線
)
```
  
**Worker 連線池參數說明**：
  
| 參數 | 值 | 說明 |
|------|-----|------|
| `max_connections` | 10 | Worker 單一程序，連線需求較低 |
| `socket_connect_timeout` | 5s | 連線建立超時時間 |
| `socket_keepalive` | True | TCP Keep-Alive 保持連線 |
  
### 5. Redis Stream 詳細機制
  
Redis Stream 是本系統的核心訊息佇列，提供**持久化、消費者群組、訊息確認**等企業級功能。
  
#### 5.1 Stream 資料結構
  
```
logs:stream (Redis Stream)
│
├─ Entry ID: 1704067200000-0
│  ├─ device_id: "device-001"
│  ├─ log_level: "INFO"
│  ├─ message: "Application started"
│  ├─ log_data: '{"version": "1.0.0"}'
│  └─ timestamp: "2024-01-01T12:00:00"
│
├─ Entry ID: 1704067200000-1
│  ├─ device_id: "device-002"
│  └─ ...
│
└─ Entry ID: 1704067200001-0
   └─ ...
```
  
**Entry ID 格式**：`<毫秒時間戳>-<序列號>`
- 時間戳：Unix 毫秒時間
- 序列號：同一毫秒內的遞增編號
- 自動生成：Redis 自動分配唯一 ID
  
#### 5.2 Stream 寫入操作 (FastAPI 端)
  
**單一日誌寫入** (`app/main.py:170-175`):
  
```python
message_id = await redis_client.xadd(
    name="logs:stream",        # Stream 名稱
    fields={                   # 訊息欄位
        "device_id": "device-001",
        "log_level": "INFO",
        "message": "Log content",
        "log_data": '{"key": "value"}',
        "timestamp": "2024-01-01T12:00:00"
    },
    maxlen=100000,             # Stream 最大長度
    approximate=True           # 使用近似裁剪
)
# 返回: b"1704067200000-0"
```
  
**Redis XADD 命令對應**：
```bash
XADD logs:stream MAXLEN ~ 100000 * device_id "device-001" log_level "INFO" ...
```
  
**maxlen 與 approximate 參數**：
  
```
┌─────────────────────────────────────────────────────────────┐
│              Stream 長度控制機制                              │
└─────────────────────────────────────────────────────────────┘
  
maxlen=100000, approximate=False (精確模式)
├─ 每次 XADD 後檢查長度
├─ 超過 100000 則刪除最舊的
└─ 效能較低（每次都要裁剪）
  
maxlen=100000, approximate=True (近似模式) ✓
├─ 允許長度暫時超過 100000
├─ 當超過較多時才批次裁剪
├─ 實際長度可能為 100000~101000
└─ 效能較高（減少裁剪頻率）
```
  
**批量寫入 (Pipeline)** (`app/main.py:206-226`):
  
```python
# 建立 Pipeline
pipe = redis_client.pipeline()
  
# 添加多個 XADD 命令（不立即執行）
for log in batch.logs:
    pipe.xadd(
        name="logs:stream",
        fields=log_dict,
        maxlen=100000,
        approximate=True
    )
  
# 一次性執行所有命令
results = await pipe.execute()
# 返回: [b"1704067200000-0", b"1704067200000-1", ...]
```
  
**Pipeline 效能提升原理**：
  
```
不使用 Pipeline：
Client ─► XADD ─► Server ─► Response ─► Client
Client ─► XADD ─► Server ─► Response ─► Client
Client ─► XADD ─► Server ─► Response ─► Client
(3 次網路往返)
  
使用 Pipeline：
Client ─► [XADD, XADD, XADD] ─► Server ─► [Resp1, Resp2, Resp3] ─► Client
(1 次網路往返)
```
  
**效能數據**：
- 單一 XADD：~0.5ms/筆
- Pipeline (100筆)：~5ms/批次 = ~0.05ms/筆
- **效能提升：10倍**
  
#### 5.3 Stream 消費操作 (Worker 端)
  
**消費者群組模式** (`app/worker.py:195-201`):
  
```python
messages = redis_client.xreadgroup(
    groupname='log_workers',       # 消費者群組名稱
    consumername='worker-1',       # Worker 識別碼
    streams={'logs:stream': '>'},  # '>' 表示只讀取新訊息
    count=100,                     # 每次最多讀取 100 筆
    block=5000                     # 阻塞等待 5000 毫秒
)
```
  
**XREADGROUP 返回格式**：
  
```python
[
    (
        'logs:stream',  # Stream 名稱
        [
            (
                '1704067200000-0',  # Entry ID
                {
                    'device_id': 'device-001',
                    'log_level': 'INFO',
                    'message': 'Log content',
                    'log_data': '{"key": "value"}',
                    'timestamp': '2024-01-01T12:00:00'
                }
            ),
            ('1704067200000-1', {...}),
            # ... 更多訊息
        ]
    )
]
```
  
**消費者群組狀態追蹤**：
  
```
┌─────────────────────────────────────────────────────────────┐
│                 消費者群組內部狀態                            │
└─────────────────────────────────────────────────────────────┘
  
Consumer Group: log_workers
│
├─ last-delivered-id: 1704067200100-0
│  (最後一個被分配出去的訊息 ID)
│
├─ consumers:
│  ├─ worker-1
│  │  ├─ pending-count: 100      (處理中的訊息數)
│  │  ├─ idle-time: 1000ms       (閒置時間)
│  │  └─ pending-entries:
│  │     ├─ 1704067200000-0 (分配時間: T1)
│  │     └─ 1704067200000-1 (分配時間: T2)
│  │
│  └─ worker-2
│     └─ pending-count: 0
│
└─ pending-entries-list (PEL):
   ├─ 總待處理訊息: 100
   ├─ 最小 ID: 1704067200000-0
   └─ 最大 ID: 1704067200099-0
```
  
#### 5.4 訊息確認機制 (ACK)
  
**確認處理完成** (`app/worker.py:219-223`):
  
```python
# 批次寫入資料庫成功後
for message_id in message_ids:
    redis_client.xack('logs:stream', 'log_workers', message_id)
```
  
**XACK 工作原理**：
  
```
處理前：
logs:stream ──────────────────────────►
              ↑
              last-delivered-id = 1704067200100-0
  
Pending Entries List (PEL):
├─ 1704067200000-0 → worker-1
├─ 1704067200000-1 → worker-1
└─ ... (100 筆)
  
處理後 (XACK):
logs:stream ──────────────────────────►
  
Pending Entries List (PEL):
└─ (空)  ✓ 所有訊息已確認
```
  
**未確認訊息的影響**：
- 訊息保留在 PEL 中
- Worker 崩潰後可重新分配
- 使用 XCLAIM 重新認領超時訊息
  
### 6. Redis 快取層詳解
  
除了 Stream 訊息佇列，Redis 也作為**查詢結果快取**，減少資料庫壓力。
  
#### 6.1 快取策略設計
  
**快取 Key 命名規範**：
  
```
┌─────────────────────────────────────────────────────────────┐
│                    快取 Key 設計                             │
└─────────────────────────────────────────────────────────────┘
  
日誌查詢快取：
├─ 格式: cache:logs:{device_id}:{limit}
├─ 範例: cache:logs:device-001:100
├─ TTL: 300 秒 (5 分鐘)
└─ 用途: 儲存特定設備的日誌列表
  
統計資料快取：
├─ 格式: cache:stats
├─ TTL: 60 秒 (1 分鐘)
└─ 用途: 系統整體統計資訊
```
  
#### 6.2 快取讀寫流程
  
**日誌查詢快取** (`app/main.py:260-314`):
  
```python
# 1. 建立快取 Key
cache_key = f"cache:logs:{device_id}:{limit}"
  
# 2. 嘗試讀取快取
cached_data = await redis_client.get(cache_key)
  
if cached_data:
    # 快取命中 (Cache Hit)
    logs_data = json.loads(cached_data)
    return BatchLogQueryResponse(
        total=len(logs_data),
        source="cache",  # 標示資料來源
        data=logs_data
    )
  
# 3. 快取未命中 (Cache Miss) - 查詢資料庫
logs = await db.execute(query)
  
# 4. 寫入快取
await redis_client.setex(
    name=cache_key,
    time=300,  # TTL 5 分鐘
    value=json.dumps(logs_data)
)
  
return BatchLogQueryResponse(
    total=len(logs_data),
    source="database",  # 標示資料來源
    data=logs_data
)
```
  
**快取流程圖**：
  
```
┌─────────────────────────────────────────────────────────────┐
│                   快取查詢決策流程                            │
└─────────────────────────────────────────────────────────────┘
  
GET /api/logs/device-001?limit=100
       │
       ▼
┌─────────────────┐
│ 建立快取 Key     │
│ cache:logs:...  │
└─────────────────┘
       │
       ▼
┌─────────────────┐     Yes    ┌─────────────────┐
│ Redis GET key   │───────────►│ 返回快取資料     │
│ 快取命中？       │            │ source="cache"  │
└─────────────────┘            └─────────────────┘
       │ No
       ▼
┌─────────────────┐
│ PostgreSQL      │
│ SELECT ... FROM │
│ logs WHERE ...  │
└─────────────────┘
       │
       ▼
┌─────────────────┐
│ Redis SETEX     │
│ TTL=300s        │
└─────────────────┘
       │
       ▼
┌─────────────────┐
│ 返回資料庫結果   │
│ source="db"     │
└─────────────────┘
```
  
#### 6.3 快取失效策略
  
**Time-To-Live (TTL) 設定**：
  
| 快取類型 | TTL | 理由 |
|----------|-----|------|
| 日誌查詢 | 300s (5分鐘) | 日誌資料變動頻繁，但短期內相同查詢可複用 |
| 統計資料 | 60s (1分鐘) | 統計查詢昂貴，但需要相對即時 |
  
**自動失效 vs 主動失效**：
  
```
自動失效 (本系統採用):
├─ 優點：實作簡單，無需追蹤資料變更
├─ 缺點：快取可能包含過期資料
└─ 適用：日誌系統（可接受短期不一致）
  
主動失效 (進階方案):
├─ 優點：資料始終一致
├─ 缺點：實作複雜，需要監聽資料變更
└─ 適用：即時性要求高的系統
```
  
### 7. Redis 雙重角色：Stream vs Cache
  
```
┌─────────────────────────────────────────────────────────────┐
│                Redis 在系統中的雙重角色                       │
└─────────────────────────────────────────────────────────────┘
  
                          Redis 512MB
              ┌────────────────────────────────┐
              │                                │
    Stream    │  ┌──────────────────────┐     │    Cache
   (寫入路徑)  │  │   logs:stream        │     │   (讀取路徑)
              │  │   (訊息佇列)          │     │
FastAPI ─────►│  │   100,000 entries    │     │◄──── FastAPI
  XADD        │  └──────────────────────┘     │        GET
              │                                │
              │  ┌──────────────────────┐     │
Worker ◄──────│  │   cache:logs:*       │     │
  XREADGROUP  │  │   cache:stats        │     │
              │  │   (查詢快取)          │     │
              │  └──────────────────────┘     │
              │                                │
              └────────────────────────────────┘
```
  
**角色比較**：
  
| 特性 | Stream (訊息佇列) | Cache (資料快取) |
|------|-------------------|------------------|
| **資料流向** | 寫入 → 消費 | 讀取 ← 快取 |
| **持久性** | 永久保存（AOF）| 有限期（TTL）|
| **Key 數量** | 1 個 Stream | 多個快取 Key |
| **資料結構** | 時序序列 | Key-Value |
| **使用命令** | XADD/XREADGROUP/XACK | GET/SETEX |
| **記憶體佔用** | ~400MB | ~100MB |
  
### 8. Redis 與 PostgreSQL 協作模式
  
```
┌─────────────────────────────────────────────────────────────┐
│              Redis + PostgreSQL 資料流完整路徑               │
└─────────────────────────────────────────────────────────────┘
  
[寫入路徑 - 高吞吐量]
Client → FastAPI → Redis Stream → Worker → PostgreSQL
                   (< 5ms)                  (~50ms/batch)
  
特點：
├─ FastAPI 只負責寫入 Redis（極快）
├─ Worker 批次處理（效率高）
└─ PostgreSQL 負責持久化（可靠）
  
[讀取路徑 - 低延遲]
Client ← FastAPI ← Redis Cache    OR    PostgreSQL
                   (< 1ms)               (< 50ms)
  
特點：
├─ 先查詢 Redis 快取
├─ 命中則直接返回（極快）
└─ 未命中才查詢資料庫
```
  
**為何這樣設計？**
  
1. **寫入解耦**：
   - FastAPI 不直接寫資料庫，避免阻塞
   - Redis Stream 作為緩衝區，吸收流量峰值
   - Worker 批次寫入，提升資料庫效率
  
2. **讀取加速**：
   - 熱門查詢結果快取在 Redis
   - 減少資料庫查詢次數
   - 降低 PostgreSQL 負載
  
3. **故障隔離**：
   - PostgreSQL 暫時故障 → 日誌仍存在 Redis Stream
   - Redis 故障 → FastAPI 可以降級處理
   - Worker 故障 → 訊息保留在 Pending List
  
## Worker 工作流程
  
### Docker Compose 配置
  
```yaml
worker:
  build:
    context: ./app
    dockerfile: Dockerfile
  container_name: log-worker
  command: python worker.py
  environment:
    - POSTGRES_HOST=postgres
    - POSTGRES_PORT=5432
    - POSTGRES_USER=loguser
    - POSTGRES_PASSWORD=logpass
    - POSTGRES_DB=logsdb
    - REDIS_HOST=redis
    - REDIS_PORT=6379
    - WORKER_NAME=worker-1
```
  
- `command: python worker.py`: 執行獨立的 Worker 腳本
- Worker 使用 Redis Stream 消費者群組模式從 'logs:stream' 讀取日誌
- 將日誌批次寫入 PostgreSQL 以提高效能
- 使用 `xreadgroup` 消費 Redis Stream 訊息
  
### Worker 核心邏輯
  
1. **訊息消費**: 從 Redis Stream 的 'log_workers' 群組中讀取訊息
2. **批次處理**: 將多個日誌訊息組成批次，提高寫入效率
3. **數據持久化**: 使用原生 SQL 批次插入到 PostgreSQL
4. **確認機制**: 處理完成後向 Redis 發送 ACK 以避免重複處理
5. **錯誤處理**: 實現了錯誤重試和容錯機制
  
## Worker 詳細實作
  
### 1. Worker 配置參數
  
**檔案位置**: `app/worker.py` (第 14-24 行)
  
```python
# 環境變數配置
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
WORKER_NAME = os.getenv('WORKER_NAME', f'worker-{int(time.time())}')
  
# Redis Stream 配置
STREAM_NAME = 'logs:stream'        # Stream 名稱（與 FastAPI 一致）
GROUP_NAME = 'log_workers'         # 消費者群組名稱
BATCH_SIZE = 100                   # 每批次處理 100 筆日誌
BLOCK_MS = 5000                    # 阻塞等待 5 秒
```
  
**關鍵配置參數**:
| 參數 | 值 | 說明 |
|------|-----|------|
| `BATCH_SIZE` | 100 | 每次讀取最多 100 筆訊息 |
| `BLOCK_MS` | 5000 | 無訊息時阻塞 5 秒後返回 |
| `STREAM_NAME` | logs:stream | Redis Stream 鍵名 |
| `GROUP_NAME` | log_workers | 消費者群組名稱 |
  
### 2. Redis 連線初始化
  
**檔案位置**: `app/worker.py` (第 44-87 行)
  
```python
def init_redis():
    """
    初始化 Redis 連線
    """
    global redis_client
  
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,        # 自動解碼
            socket_connect_timeout=5,     # 連線超時 5 秒
            socket_keepalive=True,        # 保持連線
            max_connections=10            # Worker 使用較少連線
        )
  
        # 測試連線
        redis_client.ping()
        print(f"✅ Redis 連線成功 ({REDIS_HOST}:{REDIS_PORT})")
  
        # 確保消費者群組存在
        try:
            redis_client.xgroup_create(
                name=STREAM_NAME,         # Stream 名稱
                groupname=GROUP_NAME,     # 群組名稱
                id='0',                   # 從 Stream 開頭開始
                mkstream=True             # 若 Stream 不存在則創建
            )
            print(f"✅ 建立消費者群組: {GROUP_NAME}")
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                print(f"ℹ️ 消費者群組已存在: {GROUP_NAME}")
            else:
                raise
  
        return True
  
    except Exception as e:
        print(f"❌ Redis 連線失敗: {e}")
        return False
```
  
**消費者群組創建說明**:
- **id='0'**: 從 Stream 開頭開始讀取（不跳過歷史訊息）
- **mkstream=True**: 若 Stream 不存在則自動創建
- **BUSYGROUP**: 群組已存在時的標準錯誤，可安全忽略
  
### 3. Redis Stream 消費操作
  
**檔案位置**: `app/worker.py` (第 195-201 行)
  
```python
# 從 Redis Stream 讀取訊息
messages = redis_client.xreadgroup(
    groupname=GROUP_NAME,              # 消費者群組: 'log_workers'
    consumername=WORKER_NAME,          # 唯一的 Worker 識別碼
    streams={STREAM_NAME: '>'},        # 只讀取新的未處理訊息
    count=BATCH_SIZE,                  # 最多讀取 100 筆
    block=BLOCK_MS                     # 阻塞 5000 毫秒
)
```
  
**XREADGROUP 命令參數**:
- **groupname**: 消費者群組名稱
- **consumername**: Worker 的唯一識別碼（支援多 Worker 部署）
- **streams**: 指定要讀取的 Stream，`>` 表示只讀取新訊息
- **count**: 單次讀取的最大訊息數量
- **block**: 無訊息時的阻塞等待時間（毫秒）
  
**消費者群組的優勢**:
1. **自動負載均衡**: 多個 Worker 自動分配訊息
2. **訊息追蹤**: 未確認的訊息會保留在 Pending Entries List
3. **故障恢復**: Worker 崩潰後可重新處理未確認訊息
4. **防止重複**: 同一訊息只會被一個 Worker 處理
  
### 4. 訊息解析與轉換
  
**檔案位置**: `app/worker.py` (第 132-175 行)
  
```python
def process_messages(messages):
    """
    處理從 Redis Stream 讀取的訊息
  
    參數：
        messages: Redis Stream 訊息列表
  
    返回：
        tuple: (logs_to_insert, message_ids)
  
    訊息格式:
    [
        (stream_name, [
            (message_id, {
                'device_id': 'device-001',
                'log_level': 'INFO',
                'message': 'Log content',
                'log_data': '{"key": "value"}',
                'timestamp': '2024-01-01T12:00:00'
            }),
            ...
        ]),
        ...
    ]
    """
    logs_to_insert = []
    message_ids = []
  
    for stream_name, stream_messages in messages:
        for message_id, message_data in stream_messages:
            try:
                # 解析日誌資料
                log_data_str = message_data.get('log_data', '{}')
  
                # 確保 log_data 是字串格式
                if isinstance(log_data_str, dict):
                    log_data_str = json.dumps(log_data_str)
  
                # 構建資料庫插入記錄
                log_entry = {
                    'device_id': message_data['device_id'],
                    'log_level': message_data['log_level'],
                    'message': message_data['message'],
                    'log_data': log_data_str,
                    'created_at': message_data.get('timestamp', datetime.now().isoformat())
                }
  
                logs_to_insert.append(log_entry)
                message_ids.append(message_id)
  
            except Exception as e:
                print(f"❌ 解析訊息失敗 ({message_id}): {e}")
                # 仍然記錄 message_id，以便 ACK（避免重複處理）
                message_ids.append(message_id)
  
    return logs_to_insert, message_ids
```
  
**資料轉換流程**:
1. 遍歷所有 Stream 訊息
2. 解析每個訊息的欄位
3. 確保 `log_data` 為 JSON 字串格式
4. 構建符合 PostgreSQL 表結構的字典
5. 收集所有 message_id 用於後續 ACK
  
### 5. PostgreSQL 批次寫入
  
**檔案位置**: `app/worker.py` (第 88-131 行)
  
```python
def batch_insert_logs(logs_data):
    """
    批次插入日誌到 PostgreSQL
  
    參數：
        logs_data: list of dict，包含日誌資料
  
    返回：
        bool: 是否成功
  
    使用原生 SQL 參數化查詢以獲得最佳效能
    （比 ORM 快約 3-5 倍）
    """
    if not logs_data:
        return True
  
    session = SyncSessionLocal()
  
    try:
        # 使用原生 SQL 批次插入（效能最佳）
        stmt = text("""
            INSERT INTO logs (device_id, log_level, message, log_data, created_at)
            VALUES (:device_id, :log_level, :message, CAST(:log_data AS jsonb), :created_at)
        """)
  
        # 執行批次插入（所有資料在單一交易中）
        session.execute(stmt, logs_data)
        session.commit()
  
        print(f"✅ 成功寫入 {len(logs_data)} 筆日誌到資料庫")
        return True
  
    except Exception as e:
        session.rollback()
        print(f"❌ 批次寫入失敗: {e}")
        return False
  
    finally:
        session.close()
```
  
**效能優化要點**:
- **原生 SQL**: 避免 ORM 開銷，直接使用參數化 SQL
- **CAST AS JSONB**: 確保正確的 PostgreSQL 類型轉換
- **單一交易**: 所有插入在同一交易中，保證原子性
- **批次大小**: 100 筆/批次，平衡效能與記憶體使用
  
### 6. 訊息確認機制 (ACK)
  
**檔案位置**: `app/worker.py` (第 217-224 行)
  
```python
if success:
    # ACK 已處理的訊息
    for message_id in message_ids:
        try:
            redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)
        except Exception as e:
            print(f"❌ ACK 失敗 ({message_id}): {e}")
  
    print(f"📝 處理完成: {len(logs_to_insert)} 筆日誌")
    error_count = 0  # 重置錯誤計數
```
  
**XACK 命令說明**:
- 從消費者群組的 Pending Entries List 中移除訊息
- 標記訊息已被成功處理
- 防止 Worker 崩潰後重複處理
  
**未確認訊息的處理**:
```python
# 查看未確認訊息
pending_info = redis_client.xpending(STREAM_NAME, GROUP_NAME)
# {'pending': 5, 'min': '1234-0', 'max': '1238-0', 'consumers': {...}}
  
# 重新分配超時訊息給其他 Worker
redis_client.xclaim(
    STREAM_NAME,
    GROUP_NAME,
    'worker-2',        # 新的 Worker
    min_idle_time=60000,  # 閒置超過 60 秒
    message_ids=['1234-0', '1235-0']
)
```
  
### 7. 主循環與錯誤處理
  
**檔案位置**: `app/worker.py` (第 179-263 行)
  
```python
def worker_loop():
    """
    Worker 主要工作循環
  
    處理流程:
    1. 從 Redis Stream 讀取訊息
    2. 解析並轉換訊息格式
    3. 批次寫入 PostgreSQL
    4. 確認訊息已處理
    5. 錯誤重試與容錯
    """
    global running
  
    print(f"🚀 啟動 Worker: {WORKER_NAME}")
    print(f"📊 設定: 批次大小={BATCH_SIZE}, 阻塞時間={BLOCK_MS}ms")
    print("-" * 60)
  
    error_count = 0
    max_errors = 10  # 最大連續錯誤次數
  
    while running:
        try:
            # 1. 從 Redis Stream 批次讀取訊息
            messages = redis_client.xreadgroup(
                groupname=GROUP_NAME,
                consumername=WORKER_NAME,
                streams={STREAM_NAME: '>'},
                count=BATCH_SIZE,
                block=BLOCK_MS
            )
  
            # 沒有新訊息
            if not messages:
                continue
  
            # 2. 處理訊息
            logs_to_insert, message_ids = process_messages(messages)
  
            if not logs_to_insert:
                print("⚠️ 沒有有效的日誌資料")
                continue
  
            # 3. 批次寫入 PostgreSQL
            success = batch_insert_logs(logs_to_insert)
  
            if success:
                # 4. ACK 已處理的訊息
                for message_id in message_ids:
                    try:
                        redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)
                    except Exception as e:
                        print(f"❌ ACK 失敗 ({message_id}): {e}")
  
                print(f"📝 處理完成: {len(logs_to_insert)} 筆日誌")
                error_count = 0  # 重置錯誤計數
            else:
                error_count += 1
                print(f"⚠️ 處理失敗，錯誤次數: {error_count}/{max_errors}")
  
                if error_count >= max_errors:
                    print(f"❌ 錯誤次數過多，停止 Worker")
                    break
  
                # 等待後重試
                time.sleep(5)
  
        except redis.exceptions.ConnectionError as e:
            print(f"❌ Redis 連線錯誤: {e}")
            error_count += 1
  
            if error_count >= max_errors:
                print(f"❌ 連線錯誤次數過多，停止 Worker")
                break
  
            print(f"⏳ 5秒後重新連線...")
            time.sleep(5)
  
            # 嘗試重新連線
            if not init_redis():
                print("❌ Redis 重新連線失敗")
                break
  
        except Exception as e:
            print(f"❌ Worker 發生未預期錯誤: {e}")
            error_count += 1
  
            if error_count >= max_errors:
                print(f"❌ 錯誤次數過多，停止 Worker")
                break
  
            time.sleep(1)
```
  
**錯誤處理策略**:
| 錯誤類型 | 處理方式 | 等待時間 |
|----------|----------|----------|
| 資料庫寫入失敗 | 重試 | 5 秒 |
| Redis 連線錯誤 | 重新連線 | 5 秒 |
| 一般錯誤 | 重試 | 1 秒 |
| 連續 10 次失敗 | 停止 Worker | - |
  
### 8. 優雅停機處理
  
**檔案位置**: `app/worker.py` (第 26-42 行)
  
```python
# 全域變數
running = True
redis_client = None
  
# ==========================================
# 訊號處理
# ==========================================
def signal_handler(sig, frame):
    """
    處理 SIGINT 和 SIGTERM 訊號（優雅關閉）
    """
    global running
    print(f"\n🛑 接收到訊號 {sig}，準備關閉 Worker...")
    running = False
  
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
```
  
**資源清理** (`app/worker.py` 第 267-288 行):
  
```python
def cleanup():
    """
    清理資源
    """
    global redis_client
  
    print("\n🧹 清理資源...")
  
    if redis_client:
        try:
            redis_client.close()
            print("✅ Redis 連線已關閉")
        except Exception as e:
            print(f"⚠️ 關閉 Redis 連線時發生錯誤: {e}")
  
    if sync_engine:
        try:
            sync_engine.dispose()
            print("✅ 資料庫連線池已關閉")
        except Exception as e:
            print(f"⚠️ 關閉資料庫連線池時發生錯誤: {e}")
```
  
**主程式入口** (`app/worker.py` 第 292-326 行):
  
```python
def main():
    """
    主程式入口
    """
    print("=" * 60)
    print("  📦 日誌收集系統 - 背景 Worker")
    print("=" * 60)
  
    # 初始化 Redis
    if not init_redis():
        print("❌ 無法啟動 Worker，Redis 連線失敗")
        sys.exit(1)
  
    # 測試資料庫連線
    try:
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"✅ PostgreSQL 連線成功")
    except Exception as e:
        print(f"❌ PostgreSQL 連線失敗: {e}")
        sys.exit(1)
  
    print("-" * 60)
  
    try:
        # 開始工作循環
        worker_loop()
    except KeyboardInterrupt:
        print("\n⚠️ 接收到鍵盤中斷")
    finally:
        cleanup()
        print("👋 Worker 已停止")
  
if __name__ == "__main__":
    main()
```
  
**優雅停機流程**:
1. 接收到停止信號（SIGINT 或 SIGTERM）
2. 設置 `running = False`
3. 完成當前批次處理（worker_loop 會在下一次迭代檢查 running 狀態）
4. 確認所有已處理訊息（ACK）
5. 執行 cleanup() 清理資源
6. 關閉 Redis 連線和資料庫連線池
7. 退出程式
  
**Docker 停止時的行為**:
```bash
docker-compose stop worker
# 發送 SIGTERM → 優雅停機
# 若 10 秒內未停止 → 發送 SIGKILL
```
  
## Worker 從 Redis 讀取到 PostgreSQL 寫入的完整流程
  
本節深入剖析 Worker 如何從 Redis Stream 讀取日誌資料，並批次寫入 PostgreSQL 資料庫的完整機制。
  
### 1. 資料讀寫架構概覽
  
```
┌─────────────────────────────────────────────────────────────────┐
│                  Worker 資料處理完整流程                          │
└─────────────────────────────────────────────────────────────────┘
  
[Redis Stream: logs:stream]
       │
       │ Step 1: XREADGROUP 批次讀取
       │ ├─ 消費者群組: log_workers
       │ ├─ 消費者名稱: worker-1
       │ ├─ 批次大小: 100 筆
       │ └─ 阻塞時間: 5000ms
       ▼
[Worker Memory: Raw Messages]
       │
       │ Step 2: process_messages() 解析轉換
       │ ├─ 遍歷每個訊息
       │ ├─ 解析 JSON 格式
       │ ├─ 驗證資料完整性
       │ └─ 轉換為 PostgreSQL 格式
       ▼
[Worker Memory: logs_to_insert]
       │
       │ Step 3: batch_insert_logs() 批次寫入
       │ ├─ 建立資料庫 Session
       │ ├─ 使用原生 SQL (text())
       │ ├─ 批次執行 INSERT
       │ └─ 提交交易 (commit)
       ▼
[PostgreSQL: logs table]
       │
       │ Step 4: XACK 確認處理完成
       │ ├─ 逐一確認每個 message_id
       │ └─ 從 Pending List 移除
       ▼
[Redis Stream: Message Acknowledged]
```
  
### 2. Redis 讀取階段：XREADGROUP 詳解
  
#### 2.1 XREADGROUP 命令執行
  
**檔案位置**: `app/worker.py` (第 198-204 行)
  
```python
# 從 Redis Stream 批次讀取訊息
messages = redis_client.xreadgroup(
    groupname=GROUP_NAME,              # 'log_workers'
    consumername=WORKER_NAME,          # 'worker-1' (唯一識別碼)
    streams={STREAM_NAME: '>'},        # {'logs:stream': '>'}
    count=BATCH_SIZE,                  # 100 (每批次最多讀取 100 筆)
    block=BLOCK_MS                     # 5000 (阻塞等待 5 秒)
)
```
  
**參數詳解**:
  
| 參數 | 值 | 說明 |
|------|-----|------|
| `groupname` | `'log_workers'` | 消費者群組名稱，多個 Worker 共享此群組 |
| `consumername` | `WORKER_NAME` | 當前 Worker 的唯一識別碼（如 worker-1） |
| `streams` | `{'logs:stream': '>'}` | Stream 名稱與讀取位置（`>` 表示只讀取新訊息） |
| `count` | `100` | 單次讀取的最大訊息數量 |
| `block` | `5000` | 無訊息時的阻塞等待時間（毫秒） |
  
#### 2.2 XREADGROUP 返回資料結構
  
```python
# messages 的實際格式：
[
    (
        'logs:stream',  # Stream 名稱
        [
            (
                '1704067200000-0',  # Message ID（時間戳-序列號）
                {
                    'device_id': 'device-001',
                    'log_level': 'INFO',
                    'message': 'Application started',
                    'log_data': '{"version": "1.0.0"}',
                    'timestamp': '2024-01-01T12:00:00+08:00'
                }
            ),
            (
                '1704067200001-0',  # 第二筆訊息
                {
                    'device_id': 'device-002',
                    'log_level': 'ERROR',
                    'message': 'Connection failed',
                    'log_data': '{"error_code": 500}',
                    'timestamp': '2024-01-01T12:00:01+08:00'
                }
            ),
            # ... 最多 100 筆訊息
        ]
    )
]
```
  
#### 2.3 阻塞等待機制
  
```
┌─────────────────────────────────────────────────────────────────┐
│                   XREADGROUP 阻塞等待流程                         │
└─────────────────────────────────────────────────────────────────┘
  
Worker 執行 XREADGROUP (block=5000)
       │
       ▼
┌─────────────────┐
│ Redis 檢查      │ ← 是否有新訊息？
└─────────────────┘
       │
       ├─ 有新訊息 ──────────────────────┐
       │                                 │
       │                                 ▼
       │                        ┌─────────────────┐
       │                        │ 立即返回訊息     │
       │                        │ (< 1ms)         │
       │                        └─────────────────┘
       │
       └─ 無新訊息 ────┐
                      │
                      ▼
              ┌─────────────────┐
              │ 阻塞等待         │
              │ (最多 5000ms)   │
              └─────────────────┘
                      │
                      ├─ 有新訊息到達 ─────────┐
                      │                        │
                      │                        ▼
                      │               ┌─────────────────┐
                      │               │ 返回新訊息       │
                      │               └─────────────────┘
                      │
                      └─ 超時 (5000ms) ────────┐
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │ 返回空列表 []    │
                                      │ Worker 繼續循環  │
                                      └─────────────────┘
```
  
**阻塞等待的優勢**:
- **減少 CPU 消耗**: 不用頻繁輪詢 Redis
- **即時響應**: 新訊息到達時立即返回
- **降低延遲**: 平均處理延遲降低至毫秒級
  
### 3. 訊息處理階段：process_messages() 詳解
  
#### 3.1 訊息解析與轉換
  
**檔案位置**: `app/worker.py` (第 136-177 行)
  
```python
def process_messages(messages):
    """
    處理從 Redis Stream 讀取的訊息
  
    轉換流程:
    1. Redis Stream 格式 → Python Dict
    2. 資料驗證與清理
    3. PostgreSQL 相容格式
    """
    logs_to_insert = []  # PostgreSQL 插入資料
    message_ids = []     # Redis ACK 列表
  
    # 遍歷所有 Stream（通常只有一個 'logs:stream'）
    for stream_name, stream_messages in messages:
        # 遍歷該 Stream 中的所有訊息
        for message_id, message_data in stream_messages:
            try:
                # === 資料清理與驗證 ===
  
                # 1. 處理 log_data 欄位（可能是 dict 或 string）
                log_data_str = message_data.get('log_data', '{}')
  
                # 確保 log_data 是字串格式（PostgreSQL JSONB 需要）
                if isinstance(log_data_str, dict):
                    log_data_str = json.dumps(log_data_str)
  
                # 2. 處理時間戳（使用 Asia/Taipei 時區）
                timestamp_str = message_data.get(
                    'timestamp',
                    datetime.now(ZoneInfo("Asia/Taipei")).isoformat()
                )
  
                # === 構建 PostgreSQL 插入記錄 ===
                log_entry = {
                    'device_id': message_data['device_id'],      # 設備 ID
                    'log_level': message_data['log_level'],      # 日誌級別
                    'message': message_data['message'],          # 日誌訊息
                    'log_data': log_data_str,                    # JSON 額外資料
                    'created_at': timestamp_str                  # 建立時間
                }
  
                logs_to_insert.append(log_entry)
                message_ids.append(message_id)
  
            except Exception as e:
                print(f"❌ 解析訊息失敗 ({message_id}): {e}")
                # 即使解析失敗，仍然記錄 message_id
                # 稍後 ACK 此訊息，避免重複處理
                message_ids.append(message_id)
  
    return logs_to_insert, message_ids
```
  
#### 3.2 資料轉換範例
  
**輸入 (Redis Stream 格式)**:
```python
message_data = {
    'device_id': 'device-001',
    'log_level': 'ERROR',
    'message': 'Database connection timeout',
    'log_data': '{"retry_count": 3, "timeout": 30}',  # JSON 字串
    'timestamp': '2024-01-01T12:00:00+08:00'
}
```
  
**輸出 (PostgreSQL 格式)**:
```python
log_entry = {
    'device_id': 'device-001',
    'log_level': 'ERROR',
    'message': 'Database connection timeout',
    'log_data': '{"retry_count": 3, "timeout": 30}',  # 保持 JSON 字串格式
    'created_at': '2024-01-01T12:00:00+08:00'
}
```
  
#### 3.3 錯誤處理機制
  
```
┌─────────────────────────────────────────────────────────────────┐
│               訊息解析錯誤處理策略                                │
└─────────────────────────────────────────────────────────────────┘
  
for message_id, message_data in stream_messages:
    │
    ▼
┌─────────────────┐
│ try: 解析訊息    │
└─────────────────┘
    │
    ├─ 成功 ───────────────────────┐
    │                              │
    │                              ▼
    │                     ┌─────────────────┐
    │                     │ 添加到插入列表   │
    │                     │ 添加到 ACK 列表  │
    │                     └─────────────────┘
    │
    └─ 失敗 (Exception) ───┐
                           │
                           ▼
                  ┌─────────────────┐
                  │ 記錄錯誤訊息     │
                  │ print(f"❌...") │
                  └─────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ 仍添加到 ACK 列表│
                  │ (避免重複處理)   │
                  └─────────────────┘
```
  
**設計考量**:
- **避免阻塞**: 單筆訊息解析失敗不影響其他訊息
- **防止重複**: 失敗的訊息仍然 ACK，不會無限重試
- **可觀測性**: 記錄詳細錯誤訊息，便於除錯
  
### 4. PostgreSQL 寫入階段：batch_insert_logs() 詳解
  
#### 4.1 批次插入實作
  
**檔案位置**: `app/worker.py` (第 92-131 行)
  
```python
def batch_insert_logs(logs_data):
    """
    批次插入日誌到 PostgreSQL
  
    效能優化:
    - 使用原生 SQL（比 ORM 快 3-5 倍）
    - 批次提交（減少交易開銷）
    - 參數化查詢（防止 SQL 注入）
    """
    if not logs_data:
        return True
  
    # 建立同步資料庫 Session
    session = SyncSessionLocal()
  
    try:
        # === 原生 SQL 批次插入 ===
        stmt = text("""
            INSERT INTO logs (device_id, log_level, message, log_data, created_at)
            VALUES (:device_id, :log_level, :message, CAST(:log_data AS jsonb), :created_at)
        """)
  
        # 批次執行所有插入（單一交易）
        session.execute(stmt, logs_data)
        session.commit()
  
        print(f"✅ 成功寫入 {len(logs_data)} 筆日誌到資料庫")
        return True
  
    except Exception as e:
        # 發生錯誤時回滾交易
        session.rollback()
        print(f"❌ 批次寫入失敗: {e}")
        return False
  
    finally:
        # 確保 Session 關閉
        session.close()
```
  
#### 4.2 原生 SQL vs ORM 效能比較
  
**使用原生 SQL (當前實作)**:
```python
# 單一 SQL 語句 + 批次參數
stmt = text("""
    INSERT INTO logs (device_id, log_level, message, log_data, created_at)
    VALUES (:device_id, :log_level, :message, CAST(:log_data AS jsonb), :created_at)
""")
session.execute(stmt, logs_data)  # logs_data: list of dict
```
  
**效能**: ~50ms / 100 筆
  
**使用 ORM (較慢的替代方案)**:
```python
# 為每筆資料建立 ORM 物件
for log in logs_data:
    log_obj = Log(
        device_id=log['device_id'],
        log_level=log['log_level'],
        message=log['message'],
        log_data=log['log_data'],
        created_at=log['created_at']
    )
    session.add(log_obj)
session.commit()
```
  
**效能**: ~150-200ms / 100 筆
  
**效能差異原因**:
1. ORM 需要建立 100 個 Python 物件
2. ORM 需要追蹤物件狀態（Dirty Checking）
3. ORM 產生的 SQL 語句較冗長
4. 原生 SQL 直接執行，無額外開銷
  
#### 4.3 JSONB 類型轉換
  
**重點**: `CAST(:log_data AS jsonb)`
  
```sql
-- PostgreSQL 需要明確的類型轉換
INSERT INTO logs (..., log_data, ...)
VALUES (..., CAST(:log_data AS jsonb), ...)
```
  
**為何需要 CAST？**
- SQLAlchemy `text()` 將參數視為純文字
- PostgreSQL `log_data` 欄位類型為 `JSONB`
- 必須明確告知 PostgreSQL 進行類型轉換
- 否則會出現類型不匹配錯誤
  
**錯誤示範**（未使用 CAST）:
```python
# ❌ 錯誤：會導致 PostgreSQL 類型錯誤
stmt = text("""
    INSERT INTO logs (device_id, log_level, message, log_data, created_at)
    VALUES (:device_id, :log_level, :message, :log_data, :created_at)
""")
# 錯誤訊息: column "log_data" is of type jsonb but expression is of type text
```
  
#### 4.4 批次插入流程圖
  
```
┌─────────────────────────────────────────────────────────────────┐
│              batch_insert_logs() 執行流程                        │
└─────────────────────────────────────────────────────────────────┘
  
logs_data = [
    {'device_id': 'device-001', ...},
    {'device_id': 'device-002', ...},
    ...  # 100 筆資料
]
       │
       ▼
┌─────────────────┐
│ 建立 Session     │ ← SyncSessionLocal()
└─────────────────┘
       │
       ▼
┌─────────────────┐
│ 準備 SQL 語句    │ ← text("""INSERT INTO logs ...""")
└─────────────────┘
       │
       ▼
┌─────────────────┐
│ 執行批次插入     │ ← session.execute(stmt, logs_data)
│ (單一交易)       │   PostgreSQL 接收 100 筆資料
└─────────────────┘
       │
       ├─ 成功 ───────────────────────┐
       │                              │
       │                              ▼
       │                     ┌─────────────────┐
       │                     │ session.commit()│
       │                     │ 提交交易         │
       │                     └─────────────────┘
       │                              │
       │                              ▼
       │                     ┌─────────────────┐
       │                     │ return True     │
       │                     └─────────────────┘
       │
       └─ 失敗 (Exception) ───┐
                              │
                              ▼
                     ┌─────────────────┐
                     │ session.rollback│
                     │ 回滾交易         │
                     └─────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ print 錯誤訊息   │
                     │ return False    │
                     └─────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ session.close() │ ← finally 區塊確保執行
                     └─────────────────┘
```
  
### 5. 訊息確認階段：XACK 詳解
  
#### 5.1 XACK 執行
  
**檔案位置**: `app/worker.py` (第 221-226 行)
  
```python
if success:  # batch_insert_logs() 返回 True
    # ACK 已處理的訊息
    for message_id in message_ids:
        try:
            redis_client.xack(
                STREAM_NAME,    # 'logs:stream'
                GROUP_NAME,     # 'log_workers'
                message_id      # '1704067200000-0'
            )
        except Exception as e:
            print(f"❌ ACK 失敗 ({message_id}): {e}")
```
  
#### 5.2 XACK 工作原理
  
```
┌─────────────────────────────────────────────────────────────────┐
│                Redis Stream Pending Entries List (PEL)          │
└─────────────────────────────────────────────────────────────────┘
  
[XREADGROUP 後 - 訊息分配]
  
Consumer Group: log_workers
├─ Consumer: worker-1
│  └─ Pending Entries:
│      ├─ 1704067200000-0 (分配時間: T1)
│      ├─ 1704067200000-1 (分配時間: T1)
│      ├─ ...
│      └─ 1704067200099-0 (分配時間: T1)
│      Total: 100 筆
  
[XACK 後 - 訊息確認]
  
Consumer Group: log_workers
├─ Consumer: worker-1
│  └─ Pending Entries:
│      Total: 0 筆 ✓ (所有訊息已確認)
```
  
#### 5.3 未確認訊息的影響
  
**場景 1: 正常流程**
```
XREADGROUP → process_messages → batch_insert_logs (成功) → XACK
Result: 訊息從 PEL 移除，處理完成
```
  
**場景 2: 資料庫寫入失敗**
```
XREADGROUP → process_messages → batch_insert_logs (失敗) → 不執行 XACK
Result: 訊息保留在 PEL，可重新處理
```
  
**場景 3: Worker 崩潰**
```
XREADGROUP → process_messages → batch_insert_logs (成功) → [Worker 崩潰]
Result: 訊息保留在 PEL（未 ACK），新 Worker 可使用 XCLAIM 重新處理
```
  
#### 5.4 重新處理未確認訊息
  
```bash
# 查看 Pending Entries
redis-cli XPENDING logs:stream log_workers
  
# 輸出範例:
# 1) (integer) 100                    # 待處理訊息數量
# 2) "1704067200000-0"                # 最小 ID
# 3) "1704067200099-0"                # 最大 ID
# 4) 1) 1) "worker-1"                 # 消費者
#       2) "100"                       # 該消費者的待處理數量
  
# 重新分配超時訊息（超過 60 秒未 ACK）
redis-cli XCLAIM logs:stream log_workers worker-2 60000 1704067200000-0
  
# 將 worker-1 的超時訊息分配給 worker-2
```
  
### 6. 完整處理週期時序圖
  
```
┌─────────────────────────────────────────────────────────────────┐
│          Worker 完整處理週期（100 筆日誌）                        │
└─────────────────────────────────────────────────────────────────┘
  
時間軸 (ms)    │ 操作                          │ 狀態
───────────────┼──────────────────────────────┼─────────────────
T=0            │ XREADGROUP (block=5000)      │ 阻塞等待...
               │                              │
T=2000         │ (新訊息到達 Redis)            │
               │                              │
T=2001         │ ← 返回 100 筆訊息             │ 讀取完成
               │                              │ PEL +100
               │                              │
T=2005         │ process_messages()           │ 解析中...
               │ ├─ 解析 message_id           │
               │ ├─ 轉換資料格式               │
               │ └─ 建立 logs_to_insert       │
               │                              │
T=2015         │ batch_insert_logs()          │ 資料庫寫入中...
               │ ├─ SyncSessionLocal()        │
               │ ├─ session.execute(stmt)     │
               │ └─ session.commit()          │
               │                              │
T=2065         │ ← 寫入成功                    │ PostgreSQL +100
               │                              │
T=2070         │ XACK (100 筆)                │ 確認中...
               │ ├─ xack(msg_id_1)            │
               │ ├─ xack(msg_id_2)            │
               │ └─ ...                       │
               │                              │
T=2100         │ ← 確認完成                    │ PEL -100
               │                              │
T=2100         │ print("處理完成: 100 筆")     │ 本批次結束
               │                              │
T=2101         │ XREADGROUP (block=5000)      │ 下一批次...
               │                              │ 阻塞等待...
```
  
**關鍵效能指標**:
- **XREADGROUP**: ~1ms（訊息已存在）或 <5000ms（阻塞等待）
- **process_messages()**: ~10ms / 100 筆
- **batch_insert_logs()**: ~50ms / 100 筆
- **XACK**: ~30ms / 100 筆
- **總處理時間**: ~90-100ms / 100 筆
- **理論吞吐量**: ~1,000 筆/秒/Worker
  
### 7. 錯誤處理與重試機制
  
#### 7.1 資料庫寫入失敗處理
  
```python
# worker_loop() 中的錯誤處理邏輯
success = batch_insert_logs(logs_to_insert)
  
if success:
    # 成功：ACK 訊息
    for message_id in message_ids:
        redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)
    error_count = 0  # 重置錯誤計數
else:
    # 失敗：不 ACK，增加錯誤計數
    error_count += 1
    print(f"⚠️ 處理失敗，錯誤次數: {error_count}/{max_errors}")
  
    if error_count >= max_errors:
        print(f"❌ 錯誤次數過多，停止 Worker")
        break
  
    # 等待 5 秒後重試
    time.sleep(5)
```
  
#### 7.2 錯誤處理決策樹
  
```
┌─────────────────────────────────────────────────────────────────┐
│                 Worker 錯誤處理決策樹                             │
└─────────────────────────────────────────────────────────────────┘
  
batch_insert_logs(logs_to_insert)
       │
       ▼
┌─────────────────┐
│ 是否成功？       │
└─────────────────┘
       │
       ├─ 成功 (True) ────────────────────┐
       │                                  │
       │                                  ▼
       │                         ┌─────────────────┐
       │                         │ XACK 所有訊息    │
       │                         │ error_count = 0 │
       │                         │ 繼續下一批次     │
       │                         └─────────────────┘
       │
       └─ 失敗 (False) ───┐
                          │
                          ▼
                 ┌─────────────────┐
                 │ error_count += 1│
                 └─────────────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ error_count     │
                 │ >= 10 ?         │
                 └─────────────────┘
                          │
                          ├─ 是 ──────────────────┐
                          │                       │
                          │                       ▼
                          │              ┌─────────────────┐
                          │              │ 停止 Worker      │
                          │              │ (避免無限重試)   │
                          │              └─────────────────┘
                          │
                          └─ 否 ──────────────────┐
                                                  │
                                                  ▼
                                         ┌─────────────────┐
                                         │ time.sleep(5)   │
                                         │ 等待後重試       │
                                         │ (訊息保留在 PEL)│
                                         └─────────────────┘
```
  
### 8. 多 Worker 協作機制
  
#### 8.1 消費者群組自動分配
  
```
┌─────────────────────────────────────────────────────────────────┐
│              多 Worker 訊息分配機制                               │
└─────────────────────────────────────────────────────────────────┘
  
Redis Stream: logs:stream
├─ Entry ID: 1704067200000-0
├─ Entry ID: 1704067200000-1
├─ Entry ID: 1704067200000-2
├─ Entry ID: 1704067200000-3
├─ Entry ID: 1704067200000-4
├─ Entry ID: 1704067200000-5
└─ ... (更多訊息)
  
Consumer Group: log_workers
├─ worker-1 (XREADGROUP count=100, block=5000)
│  ├─ 獲得: 1704067200000-0, 1704067200000-3, 1704067200000-6, ...
│  └─ 處理: ~33 筆
│
├─ worker-2 (XREADGROUP count=100, block=5000)
│  ├─ 獲得: 1704067200000-1, 1704067200000-4, 1704067200000-7, ...
│  └─ 處理: ~33 筆
│
└─ worker-3 (XREADGROUP count=100, block=5000)
   ├─ 獲得: 1704067200000-2, 1704067200000-5, 1704067200000-8, ...
   └─ 處理: ~34 筆
```
  
**自動分配規則**:
1. Redis 自動將新訊息分配給空閒的 Consumer
2. 分配策略：Round-Robin（輪詢）
3. 每個訊息只會被分配給一個 Consumer
4. Consumer 故障後，訊息保留在 PEL，可重新分配
  
#### 8.2 擴展 Worker 數量
  
**配置 3 個 Worker (`docker-compose.yml`)**:
```yaml
worker-1:
  command: python worker.py
  environment:
    - WORKER_NAME=worker-1
  
worker-2:
  command: python worker.py
  environment:
    - WORKER_NAME=worker-2
  
worker-3:
  command: python worker.py
  environment:
    - WORKER_NAME=worker-3
```
  
**效能提升**:
- 單 Worker: ~1,000 logs/s
- 3 Workers: ~3,000 logs/s
- N Workers: ~N × 1,000 logs/s（線性擴展）
  
### 9. 資料一致性保證
  
#### 9.1 至少一次交付 (At-Least-Once Delivery)
  
```
┌─────────────────────────────────────────────────────────────────┐
│                 至少一次交付保證機制                              │
└─────────────────────────────────────────────────────────────────┘
  
FastAPI 寫入 Redis
       │
       │ XADD logs:stream
       ▼
┌─────────────────┐
│ Redis Stream    │ ✓ 訊息已持久化
│ (AOF enabled)   │
└─────────────────┘
       │
       │ XREADGROUP
       ▼
┌─────────────────┐
│ Worker 讀取     │ ✓ 訊息在 PEL 中
│ (未 ACK)        │
└─────────────────┘
       │
       │ batch_insert_logs()
       ▼
┌─────────────────┐
│ PostgreSQL      │ ✓ 資料已寫入
└─────────────────┘
       │
       │ XACK
       ▼
┌─────────────────┐
│ Redis PEL       │ ✓ 訊息移除
│ (已確認)        │
└─────────────────┘
```
  
**保證機制**:
1. Redis AOF 確保訊息不會遺失
2. Worker 崩潰時，訊息保留在 PEL
3. 新 Worker 可重新處理未確認訊息
4. PostgreSQL 交易確保資料原子性
  
#### 9.2 潛在重複處理
  
**重複處理場景**:
```
Worker 執行順序:
1. XREADGROUP        ← 訊息分配到 Worker
2. batch_insert_logs ← PostgreSQL INSERT 成功
3. [Worker 崩潰]     ← 在 XACK 前崩潰
4. 訊息仍在 PEL      ← 未被確認
5. 新 Worker 重新處理 ← 重複 INSERT
```
  
**解決方案選項**:
  
**選項 1: 使用唯一約束**
```sql
-- 為 logs 表添加唯一約束（需要額外欄位）
ALTER TABLE logs ADD COLUMN message_id VARCHAR(50) UNIQUE;
```
  
**選項 2: 使用 UPSERT**
```sql
-- PostgreSQL UPSERT（需要唯一鍵）
INSERT INTO logs (...) VALUES (...)
ON CONFLICT (message_id) DO NOTHING;
```
  
**選項 3: 接受潛在重複**
- 日誌系統通常可容忍少量重複
- Worker 崩潰機率低
- 重複影響可忽略不計
  
### 10. 效能監控與優化
  
#### 10.1 關鍵效能指標
  
```python
# 在 worker_loop() 中添加效能監控
import time
  
start_time = time.time()
  
# 讀取訊息
messages = redis_client.xreadgroup(...)
read_time = time.time() - start_time
  
# 解析訊息
logs_to_insert, message_ids = process_messages(messages)
parse_time = time.time() - start_time - read_time
  
# 批次寫入
success = batch_insert_logs(logs_to_insert)
write_time = time.time() - start_time - read_time - parse_time
  
# ACK 確認
for message_id in message_ids:
    redis_client.xack(...)
ack_time = time.time() - start_time - read_time - parse_time - write_time
  
total_time = time.time() - start_time
  
print(f"📊 效能統計:")
print(f"  - 讀取時間: {read_time*1000:.2f}ms")
print(f"  - 解析時間: {parse_time*1000:.2f}ms")
print(f"  - 寫入時間: {write_time*1000:.2f}ms")
print(f"  - 確認時間: {ack_time*1000:.2f}ms")
print(f"  - 總處理時間: {total_time*1000:.2f}ms")
print(f"  - 吞吐量: {len(logs_to_insert)/total_time:.2f} logs/s")
```
  
#### 10.2 效能優化建議
  
**優化 PostgreSQL 連線池**:
```python
# database.py
sync_engine = create_engine(
    DATABASE_URL,
    pool_size=20,        # 增加連線池大小 (預設 10)
    max_overflow=10,     # 增加額外連線數 (預設 5)
    pool_pre_ping=True,  # 保持開啟
)
```
  
**優化批次大小**:
```python
# worker.py
BATCH_SIZE = 200  # 增加批次大小（預設 100）
```
  
**優化阻塞時間**:
```python
# worker.py
BLOCK_MS = 2000  # 減少阻塞時間（預設 5000），提升響應速度
```
  
**效能權衡**:
| 參數 | 增加 | 減少 |
|------|------|------|
| `BATCH_SIZE` | 吞吐量↑ 延遲↑ | 吞吐量↓ 延遲↓ |
| `BLOCK_MS` | 延遲↑ CPU↓ | 延遲↓ CPU↑ |
| `pool_size` | 並發↑ 記憶體↑ | 並發↓ 記憶體↓ |
  
## Worker 完整生命週期
  
### 1. Worker 啟動流程
  
```
main()
  │
  ├─ 1. 顯示啟動標題
  │     "📦 日誌收集系統 - 背景 Worker"
  │
  ├─ 2. init_redis()
  │     ├─ 建立 Redis 連線 (max_connections=10)
  │     ├─ 測試連線 (ping)
  │     └─ 創建/確認消費者群組 (xgroup_create)
  │
  ├─ 3. 測試 PostgreSQL 連線
  │     sync_engine.connect() → SELECT 1
  │
  └─ 4. worker_loop()
        └─ 進入主工作循環
```
  
### 2. Worker 主工作循環
  
```
worker_loop() [while running]
  │
  ├─ 1. xreadgroup() - 從 Redis Stream 讀取
  │     ├─ groupname: 'log_workers'
  │     ├─ consumername: WORKER_NAME
  │     ├─ streams: {'logs:stream': '>'}
  │     ├─ count: 100 (批次大小)
  │     └─ block: 5000ms (阻塞等待)
  │
  ├─ 2. process_messages() - 解析訊息
  │     ├─ 遍歷每個 (message_id, message_data)
  │     ├─ 轉換為 PostgreSQL 格式
  │     └─ 返回 (logs_to_insert, message_ids)
  │
  ├─ 3. batch_insert_logs() - 批次寫入資料庫
  │     ├─ 使用原生 SQL (text())
  │     ├─ CAST(:log_data AS jsonb)
  │     └─ 單一交易提交
  │
  └─ 4. xack() - 確認訊息已處理
        └─ 逐一確認每個 message_id
```
  
### 3. Redis Stream 與 Worker 協作機制詳解
  
#### 資料流向完整路徑
  
```
[Client Request]
       │
       ▼
[Nginx - 負載均衡]
       │
       ▼
[FastAPI Instance]
       │
       │ redis_client.xadd('logs:stream', fields)
       ▼
[Redis Stream: logs:stream]
       │
       │ redis_client.xreadgroup('log_workers', WORKER_NAME)
       ▼
[Worker - process_messages()]
       │
       │ batch_insert_logs() - 原生 SQL INSERT
       ▼
[PostgreSQL - logs table]
       │
       │ redis_client.xack() - 確認處理完成
       ▼
[Redis Stream - 移除 Pending Entry]
```
  
#### 關鍵 Redis 命令對照
  
| 組件 | Redis 命令 | 用途 | 檔案位置 |
|------|-----------|------|----------|
| **FastAPI** | `XGROUP CREATE` | 創建消費者群組 | `app/main.py:77-82` |
| **FastAPI** | `XADD logs:stream` | 寫入日誌訊息 | `app/main.py:170-175` |
| **FastAPI** | `Pipeline.XADD` | 批量寫入訊息 | `app/main.py:217-222` |
| **Worker** | `XGROUP CREATE` | 確保群組存在 | `app/worker.py:69-74` |
| **Worker** | `XREADGROUP` | 消費訊息 | `app/worker.py:195-201` |
| **Worker** | `XACK` | 確認訊息處理 | `app/worker.py:221` |
  
#### Redis Stream 配置一致性
  
```python
# FastAPI (app/main.py)
STREAM_NAME = 'logs:stream'
GROUP_NAME = 'log_workers'
MAX_LEN = 100000
  
# Worker (app/worker.py)
STREAM_NAME = 'logs:stream'
GROUP_NAME = 'log_workers'
BATCH_SIZE = 100
BLOCK_MS = 5000
```
  
### 4. Worker 錯誤處理與容錯機制
  
#### 錯誤處理分層
  
```
worker_loop()
  │
  ├─ Level 1: 訊息解析錯誤
  │   └─ process_messages() 內部處理
  │       ├─ 記錄錯誤訊息
  │       └─ 仍添加到 message_ids (避免重複處理)
  │
  ├─ Level 2: 資料庫寫入失敗
  │   └─ batch_insert_logs() 返回 False
  │       ├─ error_count += 1
  │       ├─ 等待 5 秒後重試
  │       └─ 不 ACK 訊息 (保留在 Pending)
  │
  ├─ Level 3: Redis 連線錯誤
  │   └─ redis.exceptions.ConnectionError
  │       ├─ error_count += 1
  │       ├─ 等待 5 秒
  │       └─ 重新執行 init_redis()
  │
  └─ Level 4: 未預期錯誤
      └─ Exception
          ├─ error_count += 1
          └─ 等待 1 秒後重試
```
  
#### 容錯閾值
  
```python
max_errors = 10  # 最大連續錯誤次數
  
if error_count >= max_errors:
    # 停止 Worker，避免無限重試
    break
```
  
### 5. Worker 與 Docker Compose 整合
  
#### 服務依賴關係
  
```yaml
worker:
  depends_on:
    - postgres   # 確保資料庫先啟動
    - redis      # 確保快取層先啟動
  restart: unless-stopped  # 自動重啟策略
```
  
#### 環境變數配置
  
| 變數 | 用途 | 對應程式碼 |
|------|------|------------|
| `POSTGRES_HOST` | 資料庫主機 | `database.py` |
| `POSTGRES_PORT` | 資料庫端口 | `database.py` |
| `POSTGRES_USER` | 資料庫用戶 | `database.py` |
| `POSTGRES_PASSWORD` | 資料庫密碼 | `database.py` |
| `POSTGRES_DB` | 資料庫名稱 | `database.py` |
| `REDIS_HOST` | Redis 主機 | `worker.py:17` |
| `REDIS_PORT` | Redis 端口 | `worker.py:18` |
| `WORKER_NAME` | Worker 識別碼 | `worker.py:19` |
  
### 6. 擴展多 Worker 實例
  
#### 配置方式
  
```yaml
# docker-compose.yml
worker-1:
  command: python worker.py
  environment:
    - WORKER_NAME=worker-1
  
worker-2:
  command: python worker.py
  environment:
    - WORKER_NAME=worker-2
  
worker-3:
  command: python worker.py
  environment:
    - WORKER_NAME=worker-3
```
  
#### 消費者群組自動分配
  
```
Redis Stream: logs:stream
Consumer Group: log_workers
  │
  ├─ worker-1: 消費 message-0, message-3, message-6...
  ├─ worker-2: 消費 message-1, message-4, message-7...
  └─ worker-3: 消費 message-2, message-5, message-8...
```
  
**優勢**:
- 自動負載均衡，無需手動配置
- 線性擴展吞吐量 (N Workers = N × 2000 logs/s)
- 獨立容錯，一個 Worker 故障不影響其他
  
## FastAPI 與 Worker 協作機制
  
### 1. 整體資料流向
  
```
┌─────────────────────────────────────────────────────────────────┐
│                        完整資料流程圖                             │
└─────────────────────────────────────────────────────────────────┘
  
Client HTTP Request
        │
        ▼
┌─────────────────┐
│     Nginx       │ ← 負載均衡 & 限流
└─────────────────┘
        │
        ▼
┌─────────────────┐
│    FastAPI      │ ← 請求驗證 & 處理
│   (Instance)    │
└─────────────────┘
        │
        ▼ XADD (寫入)
┌─────────────────┐
│  Redis Stream   │ ← logs:stream (緩衝區)
│  (logs:stream)  │   maxlen=100,000
└─────────────────┘
        │
        │ XREADGROUP (消費)
        ▼
┌─────────────────┐
│     Worker      │ ← 批次處理 & 持久化
│  (Consumer)     │   BATCH_SIZE=100
└─────────────────┘
        │
        ▼ INSERT (批次寫入)
┌─────────────────┐
│   PostgreSQL    │ ← 永久存儲
│   (Database)    │
└─────────────────┘
```
  
### 2. FastAPI 端的操作
  
**寫入 Redis Stream (`app/main.py`)**:
  
```python
# 單一日誌寫入
message_id = await redis_client.xadd(
    name="logs:stream",
    fields={
        "device_id": "device-001",
        "log_level": "INFO",
        "message": "Application started",
        "log_data": '{"version": "1.0.0"}',
        "timestamp": "2024-01-01T12:00:00"
    },
    maxlen=100000,
    approximate=True
)
# 返回: "1704067200000-0" (時間戳-序列號)
  
# 批量寫入（使用 Pipeline）
pipe = redis_client.pipeline()
for log in logs:
    pipe.xadd("logs:stream", fields=log_dict, maxlen=100000)
results = await pipe.execute()
# 返回: ["1704067200000-0", "1704067200000-1", ...]
```
  
**FastAPI 創建消費者群組（啟動時）**:
  
```python
@app.on_event("startup")
async def startup_event():
    # 確保消費者群組存在
    try:
        await redis_client.xgroup_create(
            name='logs:stream',
            groupname='log_workers',
            id='0',
            mkstream=True
        )
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass  # 群組已存在，無需操作
```
  
### 3. Worker 端的操作
  
**從 Redis Stream 消費 (`app/worker.py`)**:
  
```python
# 消費訊息
messages = redis_client.xreadgroup(
    groupname='log_workers',
    consumername='worker-1',
    streams={'logs:stream': '>'},
    count=100,
    block=5000
)
  
# 訊息格式:
# [
#     ('logs:stream', [
#         ('1704067200000-0', {
#             'device_id': 'device-001',
#             'log_level': 'INFO',
#             'message': 'Application started',
#             'log_data': '{"version": "1.0.0"}',
#             'timestamp': '2024-01-01T12:00:00'
#         }),
#         ('1704067200000-1', {...}),
#         ...
#     ])
# ]
  
# 處理後確認
for message_id in message_ids:
    redis_client.xack('logs:stream', 'log_workers', message_id)
```
  
### 4. Redis Stream 狀態監控
  
```bash
# 查看 Stream 資訊
redis-cli XINFO STREAM logs:stream
# length: 50000
# radix-tree-keys: 100
# radix-tree-nodes: 200
# last-generated-id: 1704067200000-0
# groups: 1
  
# 查看消費者群組
redis-cli XINFO GROUPS logs:stream
# name: log_workers
# consumers: 1
# pending: 0
# last-delivered-id: 1704067200000-0
  
# 查看待處理訊息
redis-cli XPENDING logs:stream log_workers
# pending: 0 (所有訊息已確認)
```
  
### 5. 效能指標與吞吐量
  
**FastAPI 端**:
- **響應時間**: < 5ms（寫入 Redis Stream）
- **吞吐量**: 10,000+ logs/秒（批量 API）
- **併發能力**: 200 Redis 連線 × 6 Workers = 1,200 併發請求
  
**Worker 端**:
- **批次處理**: 100 logs/批次
- **處理週期**: 5 秒阻塞等待
- **寫入延遲**: ~50-100ms/批次（包含 PostgreSQL 寫入）
- **理論吞吐量**: 2,000 logs/秒/Worker
  
**系統整體**:
| 指標 | 值 | 說明 |
|------|-----|------|
| 寫入吞吐量 | 10,000+ logs/s | FastAPI 到 Redis |
| 持久化吞吐量 | 2,000 logs/s | Worker 到 PostgreSQL |
| 緩衝容量 | 100,000 logs | Redis Stream maxlen |
| 快取 TTL | 300s / 60s | 查詢/統計快取 |
  
### 6. 故障恢復機制
  
**FastAPI 故障**:
- Nginx 自動將流量轉移到其他實例
- `max_fails=3 fail_timeout=30s` 配置
- 30 秒後自動重試故障實例
  
**Worker 故障**:
- 未確認訊息保留在 Pending Entries List
- 新 Worker 啟動後可重新處理
- 使用 XCLAIM 重新分配超時訊息
  
**Redis 故障**:
- Worker 自動重試連線（最多 10 次）
- 5 秒重試間隔
- 超過重試次數則停止 Worker
  
**PostgreSQL 故障**:
- Worker 自動重試寫入
- 訊息保留在 Redis Stream 中
- 資料庫恢復後自動繼續處理
  
### 7. 多 Worker 擴展
  
**水平擴展配置** (`docker-compose.yml`):
  
```yaml
worker-1:
  command: python worker.py
  environment:
    - WORKER_NAME=worker-1
  
worker-2:
  command: python worker.py
  environment:
    - WORKER_NAME=worker-2
  
worker-3:
  command: python worker.py
  environment:
    - WORKER_NAME=worker-3
```
  
**消費者群組自動負載均衡**:
```
logs:stream (100 筆訊息)
    │
    ├─ worker-1: 讀取訊息 0-33
    ├─ worker-2: 讀取訊息 34-66
    └─ worker-3: 讀取訊息 67-99
```
  
**優勢**:
- 自動分配，無需額外配置
- 線性擴展處理能力
- 容錯：一個 Worker 故障不影響其他
  
### 8. 資料一致性保證
  
**寫入順序保證**:
- Redis Stream 保證訊息順序
- 每個訊息有唯一 ID（時間戳-序列號）
- Worker 按順序處理同一 Stream 的訊息
  
**至少一次交付**:
- 訊息寫入 Redis 後即確認接收
- Worker 處理完成後才 ACK
- 未 ACK 的訊息可重新處理
  
**潛在重複處理**:
- Worker 崩潰在 INSERT 後、ACK 前
- 訊息可能被重複插入
- 解決方案：使用唯一約束或 UPSERT
  
## 請求處理流程
  
以下是當前端點請求如何被 Nginx 分發到 FastAPI 的詳細流程：
  
1. **請求接收**: Nginx 接收來自客戶端的 HTTP 請求
2. **路由匹配**: 根據 location 指令匹配請求路徑
3. **限流檢查**: 應用限流規則檢查是否超過速率限制
4. **負載均衡**: 根據 `least_conn` 算法選擇後端服務器
5. **請求轉發**: 通過 `proxy_pass` 指令將請求轉發到選定的 FastAPI 實例
6. **響應返回**: FastAPI 處理請求後返回響應，通過 Nginx 返回給客戶端
  
### 日誌寫入流程
  
對於日誌寫入請求 (/api/log)，處理流程如下：
  
```
Client Request -> Nginx -> FastAPI -> Redis (Queue) -> Worker -> PostgreSQL
     │             │        │
     │             │        └── 非同步處理，立即返回響應
     │             └── 負載均衡和限流
     └── HTTP Request
```
  
### Redis 到 PostgreSQL 的處理流程
  
Worker 服務持續從 Redis Stream 消費日誌資料：
  
1. **訊息消費**: 使用 `xreadgroup` 從 Redis Stream 讀取批次訊息
2. **資料轉換**: 將 Redis 中的訊息格式轉換為 PostgreSQL 相容的格式
3. **批次寫入**: 使用批次 SQL 命令將多筆資料同時寫入 PostgreSQL
4. **確認處理**: 向 Redis 發送 ACK 確認訊息已處理
5. **錯誤重試**: 如果寫入失敗，進行錯誤處理和重試
  
## 批量處理與效能優化
  
### 批量日誌端點
  
系統提供專門的批量處理端點 `/api/logs/batch`，支援一次接收多個日誌條目：
  
- 使用 Redis Pipeline 減少網路往返時間
- 批量寫入 Redis Stream 提升效能
- 在壓力測試中表現優異，支援高吞吐量
  
### 效能優化措施
  
1. **Redis 配置優化**
   - `maxmemory 512mb` 和 `maxmemory-policy allkeys-lru`: 記憶體限制和淘汰策略
   - `client_max_body_size 50M`: 支援較大的批量請求
  
2. **資料庫連線優化**
   - FastAPI 使用非同步連線池配置
   - Worker 使用同步連線池配置
   - 合適的 `pool_size` 和 `max_overflow` 設置
  
3. **Redis Stream 配置**
   - `maxlen=100000` 在 Redis 中保留最近 10 萬筆日誌
   - `approximate=True` 提升效能
  
4. **快取策略**
   - 日誌查詢結果在 Redis 中快取 5 分鐘
   - 統計資料快取 60 秒
   - 減少資料庫查詢壓力
  
### 壓力測試配置
  
根據 `tests/stress_test.py` 的配置：
- 100 台設備，每台發送 100 條日誌
- 200 並發限制，5 批次大小
- 目標：10,000 logs/秒，P95 響應時間 <100ms
  
## 性能優化配置
  
### Nginx 優化
  
1. **連線優化**
   - `worker_connections 4096`: 增加工作進程連線數
   - `keepalive 128`: 增加後端連線池大小
  
2. **超時設置**
   - 針對不同端點設置合理的超時時間
   - 避免不必要的連線佔用
  
3. **限流調優**
   - 寫入端點：高限流值以支援大量日誌輸入
   - 查詢端點：較保守的限流值以保護後端
  
### FastAPI 優化
  
1. **非同步處理**
   - 使用 async/await 處理 I/O 密集操作
   - 通過 uvicorn 多 worker 提升併發能力
   - Redis 連線池配置以支援高併發
  
2. **快取機制**
   - Redis 用作日誌隊列，實現非同步處理
   - 查詢結果快取，減少資料庫壓力
   - 使用 Redis Stream 消費者群組模式
  
3. **資料庫優化**
   - 使用 SQLAlchemy 非同步會話
   - 合理的索引和查詢優化
   - 連線池配置
  
## 健康檢查與監控
  
### 健康檢查端點
  
```nginx
location /health {
    proxy_pass http://fastapi_backend/health;
    access_log off;  # 健康檢查不記錄日誌
}
```
  
- 檢查 Redis 和 PostgreSQL 連線狀態
- 不記錄健康檢查請求日誌，避免日誌污染
  
### 監控端點
  
```nginx
location /nginx_status {
    stub_status on;
    access_log off;
    allow 127.0.0.1;  # 僅本地訪問
    deny all;         # 拒絕其他訪問
}
```
  
- 提供 Nginx 狀態資訊，便於監控
- 限制訪問權限確保安全性
  
### 錯誤處理
  
```nginx
error_page 502 503 504 /50x.html;
location = /50x.html {
    return 503 '{"error": "Service temporarily unavailable"}';
    add_header Content-Type application/json;
}
```
  
- 統一錯誤響應格式
- 提供 JSON 格式的錯誤資訊
  
## 擴展與維護
  
### 服務擴展
  
要擴展更多 FastAPI 實例，需在 nginx 配置中添加：
  
```nginx
server fastapi-n:8000 weight=1 max_fails=3 fail_timeout=30s;
```
  
同時在 docker-compose.yml 中定義相應服務容器。
  
### 配置生效
  
修改 nginx 配置後，需重啟 nginx 服務以使配置生效：
  
```bash
docker-compose restart nginx
```
  
### 監控和調優
  
- 定期檢查 Nginx 狀態端點以了解系統性能
- 監控 FastAPI 實例的資源使用情況
- 根據實際流量模式調整限流和超時設定
- 觀察 Redis 和 PostgreSQL 的性能指標
- 檢查 Worker 的處理延遲和錯誤率
  
## 總結
  
本系統通過 Nginx 與 FastAPI 的緊密配合，實現了高效能的日誌收集能力。Nginx 作為負載均衡器和反向代理，提供了請求路由、限流、健康檢查等功能；FastAPI 作為前端服務，提供了非同步處理、數據快取等功能；Worker 作為後端處理服務，實現了日誌的非同步持久化。
  
**Worker 核心特性**：
- **非同步解耦**: FastAPI 快速接收請求（<5ms），Worker 獨立處理持久化
- **批次處理**: 每次處理 100 筆日誌，使用原生 SQL 批次插入
- **消費者群組**: Redis Stream 自動分配訊息，支援多 Worker 擴展
- **容錯機制**: 完整的錯誤處理、重試邏輯和優雅停機
- **資源管理**: 連線池配置、自動清理、信號處理
  
**Redis Stream 關鍵角色**：
- **緩衝層**: 解耦 API 層與資料庫層，吸收流量峰值
- **訊息隊列**: 保證訊息順序和至少一次交付
- **負載分配**: 透過消費者群組實現自動負載均衡
- **故障恢復**: Pending Entries List 追蹤未確認訊息
  
三者結合形成了穩定、高效、可擴展的日誌收集系統架構，能夠支援高併發的日誌寫入需求並提供快速響應。
  