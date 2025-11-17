# 快速開始指南

這份指南將幫助你在 10 分鐘內完成系統的部署和測試。

## 🎯 目標

部署一個完整的日誌收集系統，包含：
- Nginx 負載平衡
- 2 個 FastAPI 實例
- 1 個背景 Worker
- Redis 快取
- PostgreSQL 資料庫

## 📋 前置需求

確保你的系統已安裝：
- Docker (>= 20.10)
- Docker Compose (>= 2.0)
- Python 3.8+ (用於壓力測試)

## 🚀 5 步驟快速開始

### 步驟 1：進入專案目錄

```bash
cd /home/claude/log-collection-system
```

### 步驟 2：啟動系統

```bash
# 使用管理腳本
./manage.sh start

# 或手動啟動
docker-compose up -d
```

預期輸出：
```
======================================================================
  啟動日誌收集系統
======================================================================
ℹ️  建構 Docker 映像檔...
ℹ️  啟動所有服務...
ℹ️  等待服務就緒...
✅ 系統啟動完成！
ℹ️  API 端點: http://localhost:8080
ℹ️  API 文件: http://localhost:8080/docs
```

### 步驟 3：驗證服務

```bash
# 檢查所有容器是否正常運行
./manage.sh status

# 或手動檢查
curl http://localhost:8080/health
```

預期回應：
```json
{
  "status": "healthy",
  "instance": "fastapi-1",
  "checks": {
    "redis": true,
    "postgres": true
  }
}
```

### 步驟 4：發送測試日誌

```bash
# 發送一筆測試日誌
curl -X POST http://localhost:8080/api/log \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "device_test",
    "log_level": "INFO",
    "message": "我的第一筆日誌！",
    "log_data": {
      "user": "polo",
      "test": true
    }
  }'
```

預期回應：
```json
{
  "status": "queued",
  "message_id": "1699960200000-0",
  "received_at": "2024-11-14T10:30:00.123456"
}
```

### 步驟 5：查詢日誌

```bash
# 等待 2 秒讓 Worker 處理日誌
sleep 2

# 查詢日誌
curl http://localhost:8080/api/logs/device_test?limit=10
```

預期回應：
```json
{
  "total": 1,
  "source": "database",
  "data": [
    {
      "id": 5,
      "device_id": "device_test",
      "log_level": "INFO",
      "message": "我的第一筆日誌！",
      "log_data": {
        "user": "polo",
        "test": true
      },
      "created_at": "2024-11-14T10:30:00"
    }
  ]
}
```

## 🧪 執行壓力測試

測試系統在高負載下的表現：

```bash
# 安裝測試依賴
pip3 install aiohttp

# 執行壓力測試（100 設備 × 100 日誌 = 10,000 筆）
./manage.sh test

# 或手動執行
cd tests
python3 stress_test.py
```

預期結果：
```
📊 請求統計：
  • 總請求數: 10,000
  • 成功請求: 10,000 (100.0%)
  • 失敗請求: 0 (0.0%)

⚡ 效能指標：
  • 吞吐量: 1,912.35 logs/秒
  • 平均回應時間: 3.45 ms
  • P95: 8.12 ms
```

## 📊 監控與除錯

### 查看即時日誌

```bash
# 查看所有服務的日誌
./manage.sh logs

# 查看特定服務的日誌
./manage.sh logs worker
./manage.sh logs fastapi-1
```

### 查看系統統計

```bash
# 使用管理腳本
./manage.sh stats

# 或手動查詢
curl http://localhost:8080/api/stats
```

### 進入資料庫

```bash
# 使用管理腳本
./manage.sh db

# 或手動進入
docker exec -it log-postgres psql -U loguser -d logsdb

# 在 PostgreSQL 中執行查詢
SELECT COUNT(*) FROM logs;
SELECT log_level, COUNT(*) FROM logs GROUP BY log_level;
SELECT * FROM logs ORDER BY created_at DESC LIMIT 10;
```

### 進入 Redis

```bash
# 使用管理腳本
./manage.sh redis

# 或手動進入
docker exec -it log-redis redis-cli

# 在 Redis 中執行命令
XLEN logs:stream
XINFO STREAM logs:stream
KEYS cache:*
```

## 🎨 訪問 API 文件

開啟瀏覽器訪問：

- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

在 Swagger UI 中你可以：
1. 查看所有 API 端點
2. 直接測試 API
3. 查看請求/回應範例

## 🛑 停止系統

```bash
# 使用管理腳本
./manage.sh stop

# 或手動停止
docker-compose down
```

## 🧹 清理系統（刪除所有資料）

```bash
# 使用管理腳本（會提示確認）
./manage.sh clean

# 或手動清理
docker-compose down -v
docker system prune -f
```

## 🔧 常見問題

### Q1: 服務啟動失敗

```bash
# 檢查 Docker 是否正常運行
docker ps

# 查看錯誤日誌
docker-compose logs

# 重新建構並啟動
docker-compose build --no-cache
docker-compose up -d
```

### Q2: 連線被拒絕

```bash
# 檢查服務是否完全啟動（等待 10 秒）
sleep 10

# 檢查端口是否被佔用
netstat -an | grep 8080
lsof -i :8080

# 如果端口被佔用，修改 docker-compose.yml 中的端口
```

### Q3: 日誌沒有寫入資料庫

```bash
# 檢查 Worker 是否正常運行
docker-compose logs worker

# 檢查 Redis Stream 是否有堆積
docker exec -it log-redis redis-cli XLEN logs:stream

# 重啟 Worker
docker-compose restart worker
```

## 📚 下一步

1. 查看完整的 [README.md](README.md) 了解更多功能
2. 閱讀 [architecture_guide.md](architecture_guide.md) 了解架構細節
3. 嘗試調整配置以優化效能
4. 整合到你的實際應用中

## 🆘 獲得幫助

如果遇到問題：

1. 查看日誌：`./manage.sh logs`
2. 檢查服務狀態：`./manage.sh status`
3. 查閱 README 的故障排除章節
4. 提交 Issue

## ✅ 檢查清單

- [ ] Docker 和 Docker Compose 已安裝
- [ ] 所有容器正常運行 (`docker-compose ps`)
- [ ] 健康檢查通過 (`curl http://localhost:8080/health`)
- [ ] 成功發送測試日誌
- [ ] 可以查詢到日誌資料
- [ ] 壓力測試通過
- [ ] 可以訪問 API 文件

恭喜！你已經成功部署了高效能日誌收集系統！🎉
