# FastAPI、Worker 與 Nginx 運作流程分析

本文件詳細說明了此日誌收集系統中 Nginx、FastAPI 應用 (`app`) 和背景 `worker` 之間的運作流程、設計模式與核心原理。

## 1. 總體架構：生產者-消費者模式

本系統的核心架構採用了經典的 **生產者-消費者 (Producer-Consumer)** 模式，並在最前端加入了 **Nginx 作為反向代理和負載均衡器**，以實現高效能、高可用性且可擴展的日誌處理流程。

- **反向代理/負載均衡器 (Reverse Proxy/Load Balancer):** `Nginx`。作為系統的唯一入口，負責接收所有客戶端請求，並根據負載均衡策略將請求分發給後端的 FastAPI 應用實例。
- **生產者 (Producer):** `FastAPI` 應用程式。其唯一職責是快速接收來自 Nginx 的請求，將日誌數據放入消息隊列，然後立即響應。
- **消費者 (Consumer):** `worker.py` 程序。它作為一個獨立的背景服務運行，持續地從消息隊列中取出日誌數據，進行處理並批量寫入 PostgreSQL 資料庫。
- **緩衝區/消息隊列 (Buffer):** `Redis Stream`。它作為生產者和消費者之間的中介，提供了一個持久化、高效的數據緩衝區，有效地將兩者解耦。

**數據流轉路徑：**

`客戶端請求` -> `Nginx (負載均衡)` -> `FastAPI 應用 (生產者)` -> `Redis Stream (緩衝區)` -> `Worker (消費者)` -> `PostgreSQL (數據庫)`

---

## 2. Nginx 負載均衡層

- **源文件:** `nginx/nginx.conf`
- **角色:** 系統的門戶，負責請求分發、負載均衡、請求限流和故障轉移。

#### 核心配置與調度方式

1.  **上游服務 (Upstream):**
    ```nginx
    upstream fastapi_backend {
        least_conn;
        server fastapi-1:8000;
        server fastapi-2:8000;
    }
    ```
    - Nginx 定義了一個名為 `fastapi_backend` 的上游服務群組，其中包含了由 `docker-compose.yml` 啟動的兩個 FastAPI 實例 (`fastapi-1` 和 `fastapi-2`)。

2.  **負載均衡策略 (調度方式):**
    - 策略採用 `least_conn` (最少連接法)。這意味著 Nginx 會將新請求發送給當前活動連接數最少的那個 FastAPI 實例。
    - **優點:** 相比默認的輪詢 (`round-robin`) 策略，`least_conn` 在處理耗時不均的請求時能更有效地分配負載，避免單一實例因處理慢請求而過載。

3.  **請求代理 (Proxy Pass):**
    ```nginx
    location /api/log {
        proxy_pass http://fastapi_backend;
        ...
    }
    ```
    - 當請求匹配到 `/api/log` 路徑時，`proxy_pass` 指令會將該請求轉發到 `fastapi_backend` 上游服務群組中的某一台服務器。

4.  **故障轉移 (Failover):**
    - `server` 指令中隱含了默認的健康檢查和故障轉移機制 (`max_fails=1`, `fail_timeout=10s`)。如果 Nginx 嘗試向上游服務器發送請求失敗，它會將該服務器標記為臨時不可用，並自動將請求轉發給群組中其他健康的服務器，從而實現服務的高可用性。

5.  **請求限流 (Rate Limiting):**
    - 配置文件中通過 `limit_req_zone` 和 `limit_req` 指令，可以對來自單一 IP 地址的請求頻率進行限制，有效防止惡意攻擊並保護後端服務的穩定性。

---

## 3. FastAPI (`app`) 服務詳解 (生產者)

- **源文件:** `app/main.py`
- **角色:** 作為系統的應用核心，提供日誌寫入的 API 接口。為了應對高併發請求，它被水平擴展為兩個實例 (`fastapi-1`, `fastapi-2`) 並由 Nginx 進行負載均衡。

#### 核心流程

1.  **接收請求:** Nginx 根據 `least_conn` 策略，將 HTTP 請求 (例如 `POST /api/log`) 轉發給其中一個 FastAPI 實例。
2.  **數據驗證:** FastAPI 使用 Pydantic 模型對傳入的日誌數據進行驗證。
3.  **推入隊列:** 驗證通過後，FastAPI 並**不直接**將日誌寫入資料庫。相反，它使用 `redis_client.xadd` 命令將日誌數據作為一條新消息添加到名為 `logs:stream` 的 Redis Stream 中。
4.  **快速響應:** 將消息推入 Redis 後，API 立即向客戶端返回 `200 OK` 響應，告知請求已被「排隊處理」。

#### 設計優勢

- **低延遲:** Redis 的內存操作速度極快，使得 API 能夠在幾毫秒內完成響應。
- **高吞吐量:** 採用異步 (`asyncio`) 模式，FastAPI 能夠高效地處理大量並發連接。
- **解耦:** API 服務與資料庫負載完全分離。

---

## 4. Worker 服務詳解 (消費者)

- **源文件:** `app/worker.py`
- **角色:** 作為一個獨立的背景服務運行，是日誌數據的最終處理者和寫入者。

#### 核心流程

1.  **監聽隊列:** Worker 啟動後會進入一個無限循環 (`worker_loop`)，使用 `redis_client.xreadgroup` 命令以**阻塞模式**等待 `logs:stream` 中出現新的日誌消息。
2.  **批量讀取:** 當有新消息時，Worker 會一次性讀取一批，以提高處理效率。
3.  **批量寫入:** Worker 將這批日誌數據整理好，執行一次性的批量 `INSERT` 操作存入 PostgreSQL。
4.  **消息確認 (Acknowledge):** 數據成功寫入後，Worker 會調用 `redis_client.xack` 命令向 Redis 發送確認信號，確保消息不會被重複消費。

#### 設計優勢

- **高效的資料庫操作:** 批量寫入大大降低了資料庫的事務開銷。
- **可靠性與數據一致性:** Redis Stream 的消息確認機制確保了即使 Worker 服務崩潰，未處理的日誌也會被重新投遞。
- **資源隔離:** Worker 的資源消耗不會影響 FastAPI 應用。

---

## 5. 核心通訊機制：Redis Stream

系統選擇 Redis Stream 作為消息隊列，主要基於以下優點：

- **持久化:** 與傳統的 Redis Pub/Sub 不同，Stream 的數據是持久化的。
- **消費者組:** 支持多個消費者協作，並能追蹤每個消費者的進度。
- **消息確認機制:** `XACK` 命令確保了「至少一次」的處理語義。

---

## 6. 容器化與擴展 (`docker-compose.yml`)

`docker-compose.yml` 文件定義了整個系統的架構：

- **服務分離:** `fastapi-1`, `fastapi-2`, `worker`, `redis`, `postgres`, `nginx` 均作為獨立的容器服務運行。
- **水平擴展:** FastAPI 服務被部署為兩個實例，由 Nginx 進行負載均衡。
- **獨立擴展:** 生產者（FastAPI）和消費者（Worker）可以根據系統瓶頸獨立進行擴展。

---

## 7. 結論

該系統通過 Nginx 實現高可用的請求分發，並利用生產者-消費者模式將**日誌接收**和**日誌處理**這兩個不同速率的操作進行解耦，構建了一個健壯、高效且可擴展的日誌收集管道。這種架構不僅提升了 API 的響應速度和用戶體驗，也確保了後端數據處理的可靠性和效率。
