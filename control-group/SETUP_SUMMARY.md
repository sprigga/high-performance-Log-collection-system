# 對照組監控系統設置總結

## 已完成項目 ✅

### 1. Prometheus Metrics 整合

**檔案**: `main_simple.py`

新增功能:
- ✅ 導入 `prometheus_client` 和 `psutil` 套件
- ✅ 定義完整的監控指標 (Counter, Histogram, Gauge)
- ✅ 在 API 端點中記錄指標
- ✅ 實作 `/metrics` 端點
- ✅ 系統資源指標更新函數
- ✅ 應用程式啟動事件處理

**監控指標類別**:
- HTTP 請求指標 (請求數、延遲)
- 日誌業務指標 (接收數、錯誤數)
- PostgreSQL 指標 (連線時間、查詢時間)
- 系統資源指標 (CPU、記憶體、磁碟)

### 2. Docker 配置更新

**檔案**: `Dockerfile`

更新內容:
- ✅ 新增 `prometheus-client==0.19.0`
- ✅ 新增 `psutil==5.9.6`
- ✅ 保留原有註釋以便追蹤變更

### 3. 監控基礎設施

**檔案**: `docker-compose-simple.yml`

新增服務:
- ✅ Prometheus (Port: 19090)
- ✅ Grafana (Port: 13000)
- ✅ PostgreSQL Exporter (Port: 19187)
- ✅ Node Exporter (Port: 19100)
- ✅ cAdvisor (Port: 18080)

新增 volumes:
- ✅ `prometheus-simple-data`
- ✅ `grafana-simple-data`

### 4. Prometheus 配置

**檔案**: `monitoring/prometheus/prometheus.yml`

配置內容:
- ✅ 全局抓取間隔設定 (15秒)
- ✅ FastAPI 指標抓取 (5秒間隔)
- ✅ PostgreSQL Exporter 配置
- ✅ Node Exporter 配置
- ✅ cAdvisor 配置
- ✅ 適當的標籤設定 (cluster, environment)

### 5. Grafana 配置

**資料源配置**: `monitoring/grafana/provisioning/datasources/prometheus.yml`
- ✅ 自動配置 Prometheus 資料源
- ✅ 設為預設資料源

**儀表板配置**: `monitoring/grafana/provisioning/dashboards/default.yml`
- ✅ 自動載入儀表板定義

**儀表板定義**: `monitoring/grafana/dashboards/control-group-dashboard.json`
- ✅ 12 個監控面板
- ✅ 完整的查詢定義
- ✅ 適當的圖表配置

### 6. 自動化腳本

**啟動腳本**: `start_monitoring.sh`
- ✅ 一鍵啟動所有服務
- ✅ 自動等待服務就緒
- ✅ 顯示訪問資訊
- ✅ 可執行權限

**停止腳本**: `stop_monitoring.sh`
- ✅ 優雅停止所有服務
- ✅ 可執行權限

**測試腳本**: `test_monitoring.sh`
- ✅ 完整的健康檢查
- ✅ 發送測試日誌
- ✅ 驗證指標更新
- ✅ 可執行權限

### 7. 文檔

**監控指南**: `MONITORING.md`
- ✅ 完整的監控系統說明
- ✅ 快速開始指引
- ✅ 指標詳細說明
- ✅ 故障排除指南
- ✅ 技術細節說明

**比較指南**: `COMPARISON.md`
- ✅ 端口配置對照表
- ✅ 同時運行兩組系統的方法
- ✅ 關鍵指標比較方法
- ✅ 測試場景建議
- ✅ 數據收集方法
- ✅ 預期效能差異

**主文檔更新**: `README.md`
- ✅ 新增監控系統說明
- ✅ 更新快速開始流程
- ✅ 連結到監控文檔

**設置總結**: `SETUP_SUMMARY.md` (本文件)
- ✅ 完整的實作清單
- ✅ 文件結構說明
- ✅ 下一步建議

## 目錄結構

```
control-group/
├── main_simple.py                 # ✅ 含 Prometheus metrics
├── Dockerfile                     # ✅ 含監控套件
├── docker-compose-simple.yml      # ✅ 含監控服務
├── monitoring/
│   ├── prometheus/
│   │   └── prometheus.yml        # ✅ Prometheus 配置
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources/
│       │   │   └── prometheus.yml # ✅ 資料源配置
│       │   └── dashboards/
│       │       └── default.yml    # ✅ 儀表板配置
│       └── dashboards/
│           └── control-group-dashboard.json # ✅ 儀表板定義
├── start_monitoring.sh            # ✅ 啟動腳本
├── stop_monitoring.sh             # ✅ 停止腳本
├── test_monitoring.sh             # ✅ 測試腳本
├── MONITORING.md                  # ✅ 監控文檔
├── COMPARISON.md                  # ✅ 比較指南
├── SETUP_SUMMARY.md               # ✅ 本文件
└── README.md                      # ✅ 主文檔 (已更新)
```

## 端口分配

| 服務 | 端口 | 說明 |
|------|------|------|
| FastAPI Simple | 18724 | 簡化版應用 |
| PostgreSQL | 15468 | 資料庫 |
| Prometheus | 19090 | 監控指標 |
| Grafana | 13000 | 視覺化 |
| PostgreSQL Exporter | 19187 | DB 指標導出 |
| Node Exporter | 19100 | 系統指標導出 |
| cAdvisor | 18080 | 容器監控 |

**特點**: 所有端口都與實驗組區隔,可同時運行兩組系統進行比較

## 關鍵特性

### 1. 與實驗組相同的監控能力

- ✅ 相同的指標類型
- ✅ 相同的 Grafana 面板佈局
- ✅ 相同的抓取間隔
- ✅ 公平的效能比較基礎

### 2. 適應簡化架構的調整

**移除的指標** (因簡化架構不適用):
- ❌ Redis Stream 相關指標
- ❌ Redis 快取指標
- ❌ Worker 處理指標
- ❌ Nginx 負載平衡指標

**保留的指標** (核心比較項目):
- ✅ HTTP 請求與延遲
- ✅ 日誌接收與錯誤
- ✅ PostgreSQL 連線與查詢
- ✅ 系統資源使用

### 3. 完整的自動化

- ✅ 一鍵啟動 (`./start_monitoring.sh`)
- ✅ 自動健康檢查
- ✅ 自動測試腳本
- ✅ 清楚的訪問資訊提示

## 測試驗證清單

### 啟動測試

```bash
cd /home/ubuntu/log-collection-system/control-group
./start_monitoring.sh
```

預期結果:
- [ ] 所有容器成功啟動
- [ ] 等待 30 秒後服務就緒
- [ ] 顯示完整的訪問資訊

### 功能測試

```bash
./test_monitoring.sh
```

預期結果:
- [ ] FastAPI 服務正常
- [ ] 健康檢查端點回應正常
- [ ] Metrics 端點有數據
- [ ] Prometheus 服務正常
- [ ] Grafana 服務正常
- [ ] 測試日誌發送成功
- [ ] 指標正確更新

### 手動驗證

1. **Grafana 儀表板** (http://localhost:13000)
   - [ ] 可以登入 (admin/admin)
   - [ ] 看到 "對照組 - 簡化系統效能儀表板"
   - [ ] 所有 12 個面板正常顯示
   - [ ] 數據開始累積

2. **Prometheus** (http://localhost:19090)
   - [ ] 可以訪問介面
   - [ ] Targets 頁面顯示所有 job 為 UP
   - [ ] 可以查詢 `http_requests_total`

3. **FastAPI Metrics** (http://localhost:18724/metrics)
   - [ ] 可以訪問
   - [ ] 看到 Prometheus 格式的指標
   - [ ] 包含自定義指標

### 壓力測試驗證

```bash
# 發送一些負載
for i in {1..100}; do
  curl -s -X POST http://localhost:18724/api/log \
    -H "Content-Type: application/json" \
    -d '{"device_id":"test-'$i'","log_level":"INFO","message":"test"}' \
    > /dev/null
done
```

在 Grafana 觀察:
- [ ] QPS 面板顯示請求
- [ ] 延遲面板有數據
- [ ] CPU 使用率變化
- [ ] 記憶體使用量變化
- [ ] PostgreSQL 連線數波動

## 與實驗組比較測試

### 同時啟動兩組系統

```bash
# Terminal 1: 啟動實驗組
cd /home/ubuntu/log-collection-system
docker-compose up -d

# Terminal 2: 啟動對照組
cd /home/ubuntu/log-collection-system/control-group
./start_monitoring.sh
```

### 並排比較

1. 開啟兩個瀏覽器視窗:
   - 實驗組: http://localhost:3000
   - 對照組: http://localhost:13000

2. 執行相同的壓力測試

3. 觀察關鍵差異:
   - QPS 吞吐量
   - P95/P99 延遲
   - 資源使用效率
   - 錯誤率

## 下一步建議

### 立即行動

1. **啟動系統**
   ```bash
   cd /home/ubuntu/log-collection-system/control-group
   ./start_monitoring.sh
   ```

2. **執行測試**
   ```bash
   ./test_monitoring.sh
   ```

3. **訪問 Grafana**
   - URL: http://localhost:13000
   - 登入: admin/admin
   - 查看儀表板

### 效能測試

1. **基準測試**
   ```bash
   python stress_test_simple.py
   ```

2. **比較測試**
   - 同時運行兩組系統
   - 執行相同測試
   - 記錄數據對比

3. **生成報告**
   ```bash
   python compare_results.py
   ```

### 進階使用

1. **自定義查詢**
   - 使用 Prometheus 查詢語言
   - 建立新的儀表板面板

2. **告警配置**
   - 設定效能閾值告警
   - 配置通知管道

3. **長期監控**
   - 增加 Prometheus 保留時間
   - 匯出歷史數據分析

## 常見問題

### Q: 為什麼有些指標沒有數據?

**A**: 某些指標需要特定操作才會產生:
- `logs_received_total`: 需要發送日誌
- `batch_processing_duration_seconds`: 需要使用批量端點
- 系統指標會自動更新

### Q: Grafana 儀表板空白?

**A**: 檢查:
1. Prometheus 是否正常運行
2. Datasource 配置是否正確
3. 時間範圍是否合適 (預設最近 1 小時)

### Q: 如何重置所有數據?

**A**:
```bash
./stop_monitoring.sh
docker-compose -f docker-compose-simple.yml down -v
./start_monitoring.sh
```

### Q: 可以同時運行實驗組和對照組嗎?

**A**: 可以! 端口已經區隔:
- 實驗組 Grafana: 3000
- 對照組 Grafana: 13000

## 技術債務

目前無重大技術債務,所有功能已完整實作。

## 致謝

監控系統參考了實驗組的設計,確保比較的公平性。

---

**文件版本**: 1.0
**最後更新**: 2025-11-19
**狀態**: ✅ 生產就緒
