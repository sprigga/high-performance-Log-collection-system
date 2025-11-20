# 快速開始指南

## 🚀 一鍵測試

### 對照組（簡化系統）

```bash
cd /home/ubuntu/log-collection-system/control-group
./run_test.sh
```

這個腳本會自動：
1. ✅ 清理舊環境
2. ✅ 啟動對照組系統
3. ✅ 等待系統就緒
4. ✅ 執行壓力測試
5. ✅ 收集測試結果

---

## 📊 手動測試步驟

### 步驟 1: 啟動系統

```bash
cd /home/ubuntu/log-collection-system/control-group
docker compose -f docker-compose-simple.yml up -d --build
```

### 步驟 2: 檢查健康狀態

```bash
# 檢查容器狀態
docker compose -f docker-compose-simple.yml ps

# 檢查 API 健康
curl http://localhost:18724/health
```

預期輸出：
```json
{
  "status": "healthy",
  "instance": "simple-fastapi",
  "checks": {
    "postgres": true
  }
}
```

### 步驟 3: 執行壓力測試

```bash
# 使用 uv（推薦）
uv run python stress_test_simple.py

# 或使用 python
python stress_test_simple.py
```

### 步驟 4: 查看結果

測試會輸出詳細的效能指標：
- ⚡ 吞吐量
- ⏱️ 回應時間（平均、P50、P95、P99）
- 📊 成功/失敗統計
- ❌ 錯誤分析

### 步驟 5: 停止系統

```bash
docker compose -f docker-compose-simple.yml down
```

---

## 🔍 常見問題

### Q1: 系統啟動失敗？

**檢查端口衝突**：
```bash
# 檢查端口 18724 是否被佔用
lsof -i :18724

# 檢查端口 15468 是否被佔用
lsof -i :15468
```

**查看日誌**：
```bash
docker compose -f docker-compose-simple.yml logs
```

### Q2: 連線資料庫失敗？

**等待資料庫啟動**：
```bash
# 檢查資料庫健康狀態
docker exec log-postgres-simple pg_isready -U loguser

# 查看資料庫日誌
docker logs log-postgres-simple
```

### Q3: 測試超時？

簡化系統效能較差，可能需要：
1. 增加超時時間（已設定為 60 秒）
2. 降低並發數（修改 `CONCURRENT_LIMIT`）
3. 減少測試資料量（修改 `NUM_DEVICES` 或 `LOGS_PER_DEVICE`）

### Q4: 如何修改測試參數？

編輯 `stress_test_simple.py`：

```python
# 測試配置
NUM_DEVICES = 100           # 設備數量
LOGS_PER_DEVICE = 100       # 每台設備日誌數
CONCURRENT_LIMIT = 200      # 並發限制
BATCH_SIZE = 5              # 批次大小
NUM_ITERATIONS = 500        # 循環次數
```

---

## 📈 比較優化系統

### 1. 測試對照組

```bash
cd /home/ubuntu/log-collection-system/control-group
./run_test.sh
```

記錄結果（範例）：
- 吞吐量: 3,500 logs/秒
- P95: 450 ms
- 失敗率: 2.5%

### 2. 測試優化系統

```bash
cd /home/ubuntu/log-collection-system
docker compose up -d --build
sleep 10
uv run python tests/stress_test.py
docker compose down
```

記錄結果（範例）：
- 吞吐量: 12,500 logs/秒
- P95: 85 ms
- 失敗率: 0%

### 3. 計算改善幅度

```bash
cd /home/ubuntu/log-collection-system/control-group
uv run python compare_results.py
```

輸出綜合分析報告。

---

## 🛠️ 進階操作

### 調整資料庫配置

編輯 `docker-compose-simple.yml`：

```yaml
postgres-simple:
  command:
    - "postgres"
    - "-c"
    - "max_connections=200"      # 調整最大連線數
    - "-c"
    - "shared_buffers=256MB"     # 調整共享緩衝
    - "-c"
    - "work_mem=8MB"             # 調整工作記憶體
```

### 查看資料庫統計

```bash
# 進入資料庫
docker exec -it log-postgres-simple psql -U loguser -d logsdb

# 查詢日誌數量
SELECT COUNT(*) FROM logs;

# 按等級統計
SELECT log_level, COUNT(*) FROM logs GROUP BY log_level;

# 查看活躍連線
SELECT count(*), state FROM pg_stat_activity GROUP BY state;
```

### 監控資源使用

```bash
# 查看容器資源
docker stats log-fastapi-simple log-postgres-simple

# 查看系統資源
top
htop
```

---

## 📝 測試檢查清單

測試前：
- [ ] 清理舊資料
- [ ] 確認端口未被佔用
- [ ] 確認系統資源充足
- [ ] 關閉其他佔用資源的程序

測試中：
- [ ] 記錄開始時間
- [ ] 觀察系統資源使用
- [ ] 監控錯誤日誌
- [ ] 截圖關鍵指標

測試後：
- [ ] 記錄測試結果
- [ ] 保存日誌檔案
- [ ] 清理測試資料
- [ ] 停止系統服務

---

## 🎯 預期結果

### 正常情況

- ✅ 系統啟動成功
- ✅ 健康檢查通過
- ✅ 測試執行完成
- ✅ 有詳細的效能數據

### 異常情況

如果出現以下情況，屬於預期內：

- ⚠️ 吞吐量較低（< 5,000 logs/秒）
- ⚠️ P95 回應時間較高（> 200 ms）
- ⚠️ 部分請求失敗（高並發下）
- ⚠️ 資料庫連線數達到上限

這些都是簡化系統的設計限制，用於對比優化的重要性。

---

## 📚 更多資訊

- [詳細 README](README.md)
- [效能比較指南](../PERFORMANCE_COMPARISON.md)
- [原系統文檔](../README.md)
