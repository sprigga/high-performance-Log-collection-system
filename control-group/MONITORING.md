# 對照組監控系統

## 概述

對照組監控系統提供與實驗組相同的監控能力,用於公平比較簡化版與優化版系統的效能差異。

## 架構

### 核心組件

1. **FastAPI 簡化版** (Port: 18724)
   - 直接寫入 PostgreSQL
   - 無連接池、無 Redis、無 Worker
   - 集成 Prometheus metrics 導出

2. **PostgreSQL** (Port: 15468)
   - 資料持久化
   - 無優化配置

3. **Prometheus** (Port: 19090)
   - 指標收集與儲存
   - 每 5-15 秒抓取一次指標

4. **Grafana** (Port: 13000)
   - 視覺化儀表板
   - 實時監控圖表
   - 預設帳號: admin/admin

### 監控組件

- **Node Exporter** (Port: 19100): 系統資源監控
- **PostgreSQL Exporter** (Port: 19187): 資料庫指標
- **cAdvisor** (Port: 18080): 容器監控

## 監控指標

### HTTP 請求指標

- `http_requests_total`: 總請求數 (按 method, endpoint, status 分類)
- `http_request_duration_seconds`: 請求延遲分佈 (P50, P95, P99)

### 日誌業務指標

- `logs_received_total`: 接收的日誌總數 (按 device_id, log_level 分類)
- `logs_processing_errors_total`: 處理錯誤總數 (按 error_type 分類)
- `batch_processing_duration_seconds`: 批量處理時間分佈

### PostgreSQL 指標

- `postgres_connection_duration_seconds`: 資料庫連線時間
- `postgres_query_duration_seconds`: 查詢執行時間 (按 operation 分類)
- `pg_stat_activity_count`: 連線數統計
- `pg_database_size_bytes`: 資料庫大小

### 系統資源指標

- `system_cpu_usage_percent`: CPU 使用率
- `system_memory_usage_bytes`: 記憶體使用量
- `system_disk_usage_bytes`: 磁碟使用量

## 快速開始

### 啟動監控系統

```bash
cd control-group
./start_monitoring.sh
```

啟動後等待約 30 秒讓所有服務完全啟動。

### 測試監控系統

```bash
./test_monitoring.sh
```

測試腳本會:
1. 檢查所有服務是否正常運行
2. 發送測試日誌
3. 驗證指標是否正確更新

### 停止監控系統

```bash
./stop_monitoring.sh
```

## 訪問監控介面

### Grafana 儀表板

1. 訪問 http://localhost:13000
2. 登入 (admin/admin)
3. 進入 "對照組 - 簡化系統效能儀表板"

### 儀表板面板說明

1. **每秒請求數 (QPS)**: 顯示總請求數、成功請求、錯誤請求
2. **HTTP 請求延遲**: P50, P95, P99 延遲時間
3. **系統 CPU 使用率**: 實時 CPU 使用百分比
4. **系統記憶體使用**: 已使用與可用記憶體
5. **每秒日誌接收數**: 按日誌等級分類的接收速率
6. **系統磁碟使用**: 磁碟空間使用情況
7. **PostgreSQL 連線時間**: 資料庫連線延遲分佈
8. **PostgreSQL 查詢時間**: 各類查詢的執行時間
9. **批量處理時間**: 批量日誌的處理延遲
10. **PostgreSQL 連線數**: 活躍、閒置與總連線數
11. **PostgreSQL 資料庫大小**: 資料庫儲存空間趨勢
12. **錯誤統計**: 各類錯誤的發生頻率

### Prometheus 查詢

訪問 http://localhost:19090 可以:
- 查詢原始指標數據
- 建立自訂查詢
- 檢查指標抓取狀態

### API 端點

- FastAPI 文檔: http://localhost:18724/docs
- Metrics 端點: http://localhost:18724/metrics
- 健康檢查: http://localhost:18724/health

## 效能測試

### 壓力測試

使用提供的壓力測試腳本:

```bash
# 在主目錄執行
python stress_test_simple.py
```

測試期間可以在 Grafana 觀察:
- 請求吞吐量變化
- 延遲時間增長
- 資源使用情況
- 錯誤率

### 與實驗組比較

同時運行兩組系統進行比較:

1. 啟動實驗組監控 (Port: 3000)
2. 啟動對照組監控 (Port: 13000)
3. 執行相同的壓力測試
4. 對比兩個 Grafana 儀表板的指標

關鍵比較指標:
- **吞吐量**: 每秒處理的請求數
- **延遲**: P95, P99 延遲時間
- **資源使用**: CPU, 記憶體使用率
- **穩定性**: 錯誤率與波動程度

## 監控配置

### Prometheus 配置

配置文件: `monitoring/prometheus/prometheus.yml`

關鍵設定:
- `scrape_interval`: 全局抓取間隔 (15秒)
- `fastapi-simple`: FastAPI 指標 (5秒間隔)
- 其他 exporters: 10秒間隔

### Grafana Dashboard 配置

儀表板 JSON: `monitoring/grafana/dashboards/control-group-dashboard.json`

- 自動重新整理: 10秒
- 時間範圍: 最近 1 小時
- 時區: Asia/Taipei

## 故障排除

### 服務無法啟動

檢查端口衝突:
```bash
# 檢查端口是否被佔用
netstat -tulpn | grep -E "18724|19090|13000|15468"
```

### Metrics 無數據

1. 檢查 FastAPI 是否正常:
```bash
curl http://localhost:18724/metrics
```

2. 檢查 Prometheus targets:
訪問 http://localhost:19090/targets

### Grafana 無法連接 Prometheus

1. 檢查 Prometheus 是否運行
2. 驗證 datasource 配置
3. 重啟 Grafana 容器

## 清理與重置

### 清理所有數據

```bash
# 停止服務
./stop_monitoring.sh

# 刪除 volumes
docker-compose -f docker-compose-simple.yml down -v

# 重新啟動
./start_monitoring.sh
```

### 重置 Grafana

```bash
docker-compose -f docker-compose-simple.yml restart grafana
```

## 技術細節

### Prometheus Metrics 實現

在 `main_simple.py` 中:

1. 使用 `prometheus_client` 庫
2. 定義 Counter, Histogram, Gauge 指標
3. 在 API 端點中記錄指標
4. `/metrics` 端點導出指標

### 系統指標更新

- 啟動時初始化
- 每次 `/metrics` 請求時更新
- 使用 `psutil` 獲取系統資源

### 與實驗組的差異

**對照組特點:**
- ❌ 無 Redis Stream
- ❌ 無 Worker 背景處理
- ❌ 無連接池
- ❌ 無負載平衡
- ✅ 有完整監控指標

**實驗組特點:**
- ✅ Redis Stream 非同步處理
- ✅ Worker 背景處理
- ✅ 連接池優化
- ✅ Nginx 負載平衡
- ✅ 有完整監控指標

## 總結

對照組監控系統提供與實驗組相同的可觀察性,使得效能比較更加公平和準確。透過 Grafana 儀表板,可以清楚看到簡化版系統在高負載下的表現,並與優化版本進行對比分析。
