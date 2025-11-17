# Nginx 與 FastAPI 配置指南

## 目錄
- [架構概述](#架構概述)
- [Nginx 配置詳解](#nginx-配置詳解)
- [FastAPI 應用設置](#fastapi-應用設置)
- [Worker 工作流程](#worker-工作流程)
- [負載均衡機制](#負載均衡機制)
- [API 端點映射](#api-端點映射)
- [性能優化配置](#性能優化配置)
- [健康檢查與監控](#健康檢查與監控)
- [請求處理流程](#請求處理流程)
- [批量處理與效能優化](#批量處理與效能優化)
- [擴展與維護](#擴展與維護)

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

## 負載均衡機制

### 路由算法

Nginx 使用 `least_conn` 算法進行負載均衡：

- 選擇當前連線數最少的後端服務器
- 適合長連線和高併發場景
- 避免某個實例過載而其他實例閒置

### 容錯機制

```nginx
server fastapi-1:8000 weight=1 max_fails=3 fail_timeout=30s;
```

- `max_fails=3`: 30 秒內失敗 3 次後暫時標記為不可用
- `fail_timeout=30s`: 暫時跳過該服務器 30 秒

### 連線複用

- `keepalive 128`: 維持 128 個空閒後端連線，提高性能
- `proxy_http_version 1.1`: 使用 HTTP/1.1 支援持久連線
- `proxy_set_header Connection ""`: 保持連線狀態

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

本系統通過 Nginx 與 FastAPI 的緊密配合，實現了高效能的日誌收集能力。Nginx 作為負載均衡器和反向代理，提供了請求路由、限流、健康檢查等功能；FastAPI 作為前端服務，提供了非同步處理、數據快取等功能；Worker 作為後端處理服務，實現了日誌的非同步持久化。三者結合形成了穩定、高效、可擴展的日誌收集系統架構，能夠支援高併發的日誌寫入需求並提供快速響應。