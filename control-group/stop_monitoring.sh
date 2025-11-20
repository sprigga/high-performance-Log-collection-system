#!/bin/bash
# 停止對照組監控系統

echo "=========================================="
echo "停止對照組監控系統"
echo "=========================================="

# 確認當前目錄
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "工作目錄: $(pwd)"

# 停止所有服務
echo ""
echo "🛑 停止所有服務..."
docker-compose -f docker-compose-simple.yml down

echo ""
echo "✅ 對照組監控系統已停止"
echo "=========================================="
