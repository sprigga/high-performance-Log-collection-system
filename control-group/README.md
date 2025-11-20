# 對照組 - 簡化系統效能測試

## 📋 概述

此對照組實作用於比較「優化系統」與「簡化系統」的效能差異。

### 系統架構比較

| 特性 | 優化系統 | 簡化系統（對照組） |
|------|---------|------------------|
| **負載平衡** | ✅ Nginx 負載平衡 | ❌ 單一 FastAPI 實例 |
| **應用實例** | ✅ 2個 FastAPI 實例 | ❌ 1個 FastAPI 實例 |
| **連接池** | ✅ SQLAlchemy 連接池 | ❌ 每次請求創建新連線 |
| **快取層** | ✅ Redis 快取 + Stream | ❌ 無快取 |
| **非同步處理** | ✅ Redis Stream + Worker | ❌ 直接同步寫入 |
| **批量操作** | ✅ Redis Pipeline | ❌ 基本批量 INSERT |

---

## 🔥 新功能: 完整監控系統

### 監控組件

- **Prometheus** (Port: 19090): 指標收集
- **Grafana** (Port: 13000): 視覺化儀表板
- **PostgreSQL Exporter**: 資料庫監控
- **Node Exporter**: 系統資源監控
- **cAdvisor**: 容器監控

### 一鍵啟動監控

```bash
./start_monitoring.sh
```

訪問 Grafana: http://localhost:13000 (admin/admin)

詳細說明: [MONITORING.md](MONITORING.md) | [效能比較指南](COMPARISON.md)

---

## 🚀 快速開始

### 方式 1: 使用監控腳本 (推薦)

```bash
cd /home/ubuntu/log-collection-system/control-group
# 啟動包含監控的完整系統
./start_monitoring.sh
```

### 方式 2: 僅啟動基本系統

```bash
cd /home/ubuntu/log-collection-system/control-group
docker compose -f docker-compose-simple.yml up -d --build
```

### 2. 檢查系統狀態

```bash
# 檢查容器狀態
docker compose -f docker-compose-simple.yml ps

# 檢查健康狀態
curl http://localhost:18724/health

# 查看 API 文檔
open http://localhost:18724/docs
```

### 3. 執行壓力測試

```bash
# 使用 uv 切換環境並執行測試
uv run python stress_test_simple.py
```

### 4. 停止系統

```bash
docker compose -f docker-compose-simple.yml down
```

---

## 📊 測試配置

### 測試參數

```python
NUM_DEVICES = 100           # 設備數量
LOGS_PER_DEVICE = 100       # 每台設備發送的日誌數
TOTAL_LOGS = 10,000         # 總日誌數
CONCURRENT_LIMIT = 200      # 並發限制
BATCH_SIZE = 5              # 批次大小
NUM_ITERATIONS = 500        # 測試循環次數
```

### 系統端點

- **API**: http://localhost:18724
- **PostgreSQL**: localhost:15468
- **Health Check**: http://localhost:18724/health
- **API Docs**: http://localhost:18724/docs

---

## 🎯 預期效能差異

### 優化系統（原系統）

- **吞吐量**: ~10,000 logs/秒
- **P95 回應時間**: < 100 ms
- **失敗率**: 0%

### 簡化系統（對照組）

- **吞吐量**: 預期較低（每次請求創建連線開銷大）
- **P95 回應時間**: 預期較高（無快取、無非同步）
- **失敗率**: 可能較高（高並發下連線數限制）

---

## 📈 效能瓶頸分析

### 簡化系統的主要瓶頸

1. **連線管理開銷**
   - 每次請求都需要建立新的 PostgreSQL 連線
   - 連線建立和關閉耗時（~10-50ms per connection）

2. **同步阻塞**
   - 直接寫入資料庫，等待 I/O 完成
   - 無法並行處理多個請求

3. **無快取層**
   - 無法利用 Redis 快速回應
   - 每次查詢都需要訪問資料庫

4. **單一實例**
   - 無負載平衡
   - CPU 和記憶體資源受限於單一容器

5. **資料庫壓力**
   - 所有寫入操作直接衝擊資料庫
   - 高並發下可能達到連線數上限（max_connections=200）

---

## 🔧 測試步驟

### 完整測試流程

```bash
# 1. 清理舊資料
docker compose -f docker-compose-simple.yml down -v

# 2. 啟動對照組系統
docker compose -f docker-compose-simple.yml up -d --build

# 3. 等待系統就緒
sleep 10

# 4. 執行壓力測試
uv run python stress_test_simple.py

# 5. 收集測試結果
# （測試腳本會自動輸出詳細的效能指標）

# 6. 停止系統
docker compose -f docker-compose-simple.yml down
```

---

## 📝 測試結果記錄

### 測試環境

- **CPU**: _____
- **記憶體**: _____
- **作業系統**: Linux WSL2
- **測試日期**: _____

### 效能指標

| 指標 | 優化系統 | 簡化系統 | 差異 |
|------|---------|---------|------|
| 吞吐量 (logs/秒) | _____ | _____ | _____ |
| 平均回應時間 (ms) | _____ | _____ | _____ |
| P50 回應時間 (ms) | _____ | _____ | _____ |
| P95 回應時間 (ms) | _____ | _____ | _____ |
| P99 回應時間 (ms) | _____ | _____ | _____ |
| 失敗率 (%) | _____ | _____ | _____ |
| 總耗時 (秒) | _____ | _____ | _____ |

---

## 🔍 監控和除錯

### 查看日誌

```bash
# FastAPI 日誌
docker logs log-fastapi-simple -f

# PostgreSQL 日誌
docker logs log-postgres-simple -f
```

### 查看資料庫狀態

```bash
# 進入 PostgreSQL 容器
docker exec -it log-postgres-simple psql -U loguser -d logsdb

# 查詢日誌數量
SELECT COUNT(*) FROM logs;

# 查詢最近的日誌
SELECT * FROM logs ORDER BY created_at DESC LIMIT 10;

# 查看活躍連線數
SELECT count(*) FROM pg_stat_activity;
```

### 效能分析

```bash
# 查看容器資源使用
docker stats log-fastapi-simple log-postgres-simple

# 查看 PostgreSQL 連線統計
docker exec log-postgres-simple psql -U loguser -d logsdb -c \
  "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"
```

---

## 💡 改善建議

根據測試結果，可以逐步加入優化：

1. **第一階段：連接池**
   - 加入 SQLAlchemy 連接池
   - 預期改善：減少連線建立開銷

2. **第二階段：非同步處理**
   - 使用 Redis Stream 作為緩衝
   - 預期改善：降低回應時間

3. **第三階段：負載平衡**
   - 加入 Nginx + 多個 FastAPI 實例
   - 預期改善：提升吞吐量

4. **第四階段：快取層**
   - 加入 Redis 查詢快取
   - 預期改善：加速查詢效能

---

## ⚠️ 注意事項

1. **測試前清理資料**
   - 確保每次測試都從乾淨狀態開始
   - 避免累積資料影響效能

2. **並發限制**
   - 簡化系統可能無法承受高並發
   - 建議從較小的並發數開始測試

3. **超時設定**
   - 簡化系統回應較慢，增加超時時間到 60 秒

4. **資料庫連線數**
   - PostgreSQL max_connections=200
   - 簡化系統高並發可能達到上限

---

## 📚 參考資料

- [FastAPI 官方文檔](https://fastapi.tiangolo.com/)
- [PostgreSQL 效能調校](https://www.postgresql.org/docs/current/performance-tips.html)
- [資料庫連接池最佳實踐](https://docs.sqlalchemy.org/en/20/core/pooling.html)
