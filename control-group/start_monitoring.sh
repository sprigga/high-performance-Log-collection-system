#!/bin/bash
# 啟動對照組監控系統

echo "=========================================="
echo "啟動對照組監控系統"
echo "=========================================="

# 確認當前目錄
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "工作目錄: $(pwd)"

# 檢查 docker-compose 檔案是否存在
if [ ! -f "docker-compose-simple.yml" ]; then
    echo "❌ 錯誤: docker-compose-simple.yml 不存在"
    exit 1
fi

# 啟動所有服務
echo ""
echo "🚀 啟動所有服務..."
docker-compose -f docker-compose-simple.yml up -d

# 等待服務啟動
echo ""
echo "⏳ 等待服務啟動 (30秒)..."
sleep 30

# 檢查服務狀態
echo ""
echo "📊 檢查服務狀態..."
docker-compose -f docker-compose-simple.yml ps

# 顯示訪問資訊
echo ""
echo "=========================================="
echo "✅ 對照組監控系統已啟動"
echo "=========================================="
echo ""
echo "服務訪問地址:"
echo "  • FastAPI 簡化版:  http://localhost:18724"
echo "  • FastAPI Docs:    http://localhost:18724/docs"
echo "  • FastAPI Metrics: http://localhost:18724/metrics"
echo "  • Prometheus:      http://localhost:19090"
echo "  • Grafana:         http://localhost:13000 (admin/admin)"
echo "  • PostgreSQL:      localhost:15468"
echo ""
echo "監控組件:"
echo "  • Node Exporter:   http://localhost:19100"
echo "  • Postgres Exporter: http://localhost:19187"
echo "  • cAdvisor:        http://localhost:18080"
echo ""
echo "使用 './stop_monitoring.sh' 停止所有服務"
echo "=========================================="
