#!/bin/bash

# 對照組壓力測試執行腳本
# 用途：自動化啟動系統、執行測試、收集結果

set -e  # 遇到錯誤立即退出

echo "========================================="
echo "  對照組 - 簡化系統壓力測試"
echo "========================================="

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 步驟 1: 清理舊環境
echo -e "\n${YELLOW}[步驟 1/5]${NC} 清理舊環境..."
docker compose -f docker-compose-simple.yml down -v 2>/dev/null || true
echo -e "${GREEN}✓${NC} 環境清理完成"

# 步驟 2: 啟動系統
echo -e "\n${YELLOW}[步驟 2/5]${NC} 啟動對照組系統..."
docker compose -f docker-compose-simple.yml up -d --build

# 步驟 3: 等待系統就緒
echo -e "\n${YELLOW}[步驟 3/5]${NC} 等待系統就緒..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:18724/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} 系統已就緒"
        break
    fi
    attempt=$((attempt + 1))
    echo "等待中... ($attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "${RED}✗${NC} 系統啟動失敗，請檢查日誌"
    docker compose -f docker-compose-simple.yml logs
    exit 1
fi

# 步驟 4: 執行壓力測試
echo -e "\n${YELLOW}[步驟 4/5]${NC} 執行壓力測試..."
echo "========================================="

# 使用 uv 或 python 執行測試
if command -v uv &> /dev/null; then
    echo "使用 uv 執行測試..."
    uv run python stress_test_simple.py
else
    echo "使用 python 執行測試..."
    python stress_test_simple.py
fi

# 步驟 5: 顯示資料庫統計
echo -e "\n${YELLOW}[步驟 5/5]${NC} 收集資料庫統計..."
echo "========================================="

# 查詢總日誌數
TOTAL_LOGS=$(docker exec log-postgres-simple psql -U loguser -d logsdb -t -c "SELECT COUNT(*) FROM logs;" 2>/dev/null || echo "0")
echo "📊 資料庫中總日誌數: $(echo $TOTAL_LOGS | xargs)"

# 查詢連線統計
echo -e "\n📊 資料庫連線統計:"
docker exec log-postgres-simple psql -U loguser -d logsdb -c \
    "SELECT count(*) as conn_count, state FROM pg_stat_activity GROUP BY state;" 2>/dev/null || true

echo -e "\n========================================="
echo -e "${GREEN}測試完成！${NC}"
echo "========================================="

# 詢問是否停止系統
echo -e "\n${YELLOW}是否停止系統？ (y/N)${NC}"
read -r -t 10 response || response="n"

if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "停止系統..."
    docker compose -f docker-compose-simple.yml down
    echo -e "${GREEN}✓${NC} 系統已停止"
else
    echo "系統保持運行中"
    echo "若要停止，請執行: docker compose -f docker-compose-simple.yml down"
fi
