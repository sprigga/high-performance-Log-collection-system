# 實驗組 vs 對照組監控比較指南

## 概述

本文件說明如何使用監控系統比較實驗組(優化版)與對照組(簡化版)的效能差異。

## 監控端口配置

### 實驗組 (優化版)

| 服務 | 端口 | 說明 |
|------|------|------|
| Nginx | 18723 | 負載平衡器 |
| FastAPI-1 | - | 內部服務 |
| FastAPI-2 | - | 內部服務 |
| Worker | - | 背景處理 |
| Redis | 16891 | 快取與 Stream |
| PostgreSQL | 15467 | 資料庫 |
| Prometheus | 9090 | 監控指標 |
| Grafana | 3000 | 視覺化 |

### 對照組 (簡化版)

| 服務 | 端口 | 說明 |
|------|------|------|
| FastAPI Simple | 18724 | 單一服務 |
| PostgreSQL | 15468 | 資料庫 |
| Prometheus | 19090 | 監控指標 |
| Grafana | 13000 | 視覺化 |

## 同時運行兩組系統

### 啟動實驗組

```bash
cd /home/ubuntu/log-collection-system
docker-compose up -d
```

訪問: http://localhost:3000 (Grafana)

### 啟動對照組

```bash
cd /home/ubuntu/log-collection-system/control-group
./start_monitoring.sh
```

訪問: http://localhost:13000 (Grafana)

## 比較方法

### 1. 並排比較 Grafana 儀表板

開啟兩個瀏覽器視窗:
- 視窗 1: http://localhost:3000 (實驗組)
- 視窗 2: http://localhost:13000 (對照組)

### 2. 執行相同的壓力測試

#### 測試實驗組

```bash
cd /home/ubuntu/log-collection-system
python tests/stress_test.py
```

#### 測試對照組

```bash
cd /home/ubuntu/log-collection-system/control-group
python stress_test_simple.py
```

### 3. 關鍵指標比較

#### 吞吐量 (Throughput)

**指標**: `每秒請求數 (QPS)` 面板

比較:
- 實驗組的 QPS 峰值
- 對照組的 QPS 峰值
- 穩定性 (波動程度)

預期結果:
- ✅ 實驗組: 更高的 QPS
- ❌ 對照組: 較低的 QPS,可能受連線建立影響

#### 延遲 (Latency)

**指標**: `HTTP 請求延遲 (P50, P95, P99)` 面板

比較:
- P50 延遲差異
- P95 延遲差異
- P99 長尾延遲

預期結果:
- ✅ 實驗組: 較低且穩定的延遲
- ❌ 對照組: 較高的延遲,尤其是 P99

#### CPU 使用率

**指標**: `系統 CPU 使用率` 面板

比較:
- 平均 CPU 使用率
- 峰值 CPU 使用率
- CPU 利用效率

預期結果:
- ✅ 實驗組: 更有效率的 CPU 使用
- ❌ 對照組: 可能較高的 CPU 使用(頻繁建立連線)

#### 記憶體使用

**指標**: `系統記憶體使用` 面板

比較:
- 記憶體使用量
- 記憶體增長趨勢

預期結果:
- ✅ 實驗組: Redis 會使用額外記憶體,但整體更穩定
- ❌ 對照組: 記憶體使用較低,但可能有鋸齒狀波動

#### 資料庫連線

**實驗組獨有**: `Redis Stream 大小` 面板
**兩組共有**: `PostgreSQL 連線數` 面板

比較:
- 資料庫活躍連線數
- 連線創建頻率

預期結果:
- ✅ 實驗組: 穩定的連線池,連線數平穩
- ❌ 對照組: 連線數頻繁波動 (每次請求創建)

#### 錯誤率

**指標**: `錯誤統計` 面板

比較:
- 總錯誤數
- 錯誤類型分佈

預期結果:
- ✅ 實驗組: 更低的錯誤率
- ❌ 對照組: 高負載下可能出現連線超時錯誤

## 測試場景

### 場景 1: 低負載測試

**目的**: 驗證基本功能

```python
# 實驗組
python tests/stress_test.py --requests 100 --concurrent 10

# 對照組
python stress_test_simple.py --requests 100 --concurrent 10
```

**預期**: 兩組系統表現相近

### 場景 2: 中負載測試

**目的**: 觀察優化效果

```python
# 實驗組
python tests/stress_test.py --requests 1000 --concurrent 50

# 對照組
python stress_test_simple.py --requests 1000 --concurrent 50
```

**預期**: 實驗組開始顯示優勢

### 場景 3: 高負載測試

**目的**: 測試極限效能

```python
# 實驗組
python tests/stress_test.py --requests 5000 --concurrent 200

# 對照組
python stress_test_simple.py --requests 5000 --concurrent 200
```

**預期**: 實驗組大幅領先,對照組可能出現錯誤

### 場景 4: 持續負載測試

**目的**: 測試穩定性

```python
# 實驗組
python tests/stress_test.py --duration 300 --concurrent 100

# 對照組
python stress_test_simple.py --duration 300 --concurrent 100
```

**預期**: 實驗組更穩定,對照組可能出現資源耗盡

## 數據收集

### 從 Prometheus 導出數據

#### 實驗組

```bash
curl "http://localhost:9090/api/v1/query?query=http_requests_total" > experimental_qps.json
curl "http://localhost:9090/api/v1/query?query=http_request_duration_seconds" > experimental_latency.json
```

#### 對照組

```bash
curl "http://localhost:19090/api/v1/query?query=http_requests_total" > control_qps.json
curl "http://localhost:19090/api/v1/query?query=http_request_duration_seconds" > control_latency.json
```

### 使用比較腳本

```bash
cd /home/ubuntu/log-collection-system/control-group
python compare_results.py
```

## 架構差異總結

### 實驗組優勢

1. **非同步處理**: Redis Stream + Worker 解耦請求處理
2. **連接池**: 資料庫連線重用,減少建立開銷
3. **負載平衡**: Nginx 分散請求到多個 FastAPI 實例
4. **快取機制**: Redis 減少資料庫查詢
5. **水平擴展**: 可輕鬆增加 FastAPI 實例與 Worker

### 對照組限制

1. **同步處理**: 每個請求直接寫入資料庫
2. **無連接池**: 每次請求創建新連線
3. **單一實例**: 無法水平擴展
4. **無快取**: 所有查詢直接打資料庫
5. **阻塞 I/O**: 長時間的資料庫操作阻塞請求

## 預期效能差異

| 指標 | 實驗組 | 對照組 | 差異倍數 |
|------|--------|--------|---------|
| QPS (低負載) | ~200 req/s | ~150 req/s | 1.3x |
| QPS (高負載) | ~1000 req/s | ~200 req/s | 5x |
| P95 延遲 (低負載) | ~10ms | ~20ms | 2x |
| P95 延遲 (高負載) | ~50ms | ~500ms | 10x |
| 錯誤率 (高負載) | <1% | 5-10% | 10x |
| 資源效率 | 高 | 低 | - |

## 監控截圖建議

建議截圖以下面板進行對比:

1. **每秒請求數**: 顯示吞吐量差異
2. **HTTP 請求延遲**: 顯示延遲分佈
3. **系統 CPU 使用率**: 顯示資源效率
4. **PostgreSQL 連線數**: 顯示連線管理差異
5. **錯誤統計**: 顯示穩定性差異

## 結論撰寫建議

基於監控數據,效能報告應包含:

1. **測試環境**: 硬體配置、Docker 資源限制
2. **測試方法**: 負載模式、測試時間
3. **關鍵指標**: QPS、延遲、錯誤率
4. **效能差異**: 具體數字與倍數
5. **瓶頸分析**: 找出限制因素
6. **優化建議**: 基於數據的改進方向

## 故障排除

### 兩組系統端口衝突

確保使用不同端口:
- 檢查 docker-compose.yml 配置
- 使用 `netstat -tulpn` 查看端口佔用

### Prometheus 數據不同步

- 檢查時間範圍設定
- 確認兩個 Prometheus 的 scrape_interval 相同
- 同步開始測試時間點

### 測試結果不一致

- 確保測試參數完全相同
- 等待系統穩定後再開始測試
- 重複測試多次取平均值

## 總結

透過完整的監控系統,可以清楚量化實驗組的優化效果。對照組提供了公平的基準線,使得效能提升的數據更具說服力。
