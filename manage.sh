#!/bin/bash

# ==========================================
# 日誌收集系統管理腳本
# ==========================================

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 函數：顯示標題
print_header() {
    echo -e "${BLUE}======================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}======================================================================${NC}"
}

# 函數：顯示成功訊息
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# 函數：顯示錯誤訊息
print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 函數：顯示警告訊息
print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# 函數：顯示資訊訊息
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# 函數：檢查 Docker 是否安裝
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安裝，請先安裝 Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose 未安裝，請先安裝 Docker Compose"
        exit 1
    fi
    
    print_success "Docker 環境檢查通過"
}

# 函數：啟動系統
start_system() {
    print_header "啟動日誌收集系統"
    
    print_info "建構 Docker 映像檔..."
    docker-compose build
    
    print_info "啟動所有服務..."
    docker-compose up -d
    
    print_info "等待服務就緒..."
    sleep 5
    
    # 檢查服務狀態
    check_services
    
    print_success "系統啟動完成！"
    print_info "API 端點: http://localhost:8080"
    print_info "API 文件: http://localhost:8080/docs"
}

# 函數：停止系統
stop_system() {
    print_header "停止日誌收集系統"
    
    docker-compose down
    
    print_success "系統已停止"
}

# 函數：重啟系統
restart_system() {
    print_header "重啟日誌收集系統"
    
    stop_system
    sleep 2
    start_system
}

# 函數：檢查服務狀態
check_services() {
    print_header "服務健康檢查"
    
    # 檢查容器狀態
    print_info "容器狀態："
    docker-compose ps
    
    echo ""
    
    # 檢查 API 健康狀態
    print_info "檢查 API 健康狀態..."
    sleep 2
    
    if curl -s http://localhost:8080/health > /dev/null; then
        print_success "API 服務正常"
        curl -s http://localhost:8080/health | python3 -m json.tool
    else
        print_error "API 服務異常"
    fi
}

# 函數：查看日誌
view_logs() {
    print_header "查看服務日誌"
    
    if [ -z "$1" ]; then
        print_info "顯示所有服務日誌（按 Ctrl+C 退出）"
        docker-compose logs -f
    else
        print_info "顯示 $1 服務日誌（按 Ctrl+C 退出）"
        docker-compose logs -f "$1"
    fi
}

# 函數：執行壓力測試
run_stress_test() {
    print_header "執行壓力測試"
    
    # 檢查 Python 是否安裝
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 未安裝"
        exit 1
    fi
    
    # 檢查 aiohttp 是否安裝
    if ! python3 -c "import aiohttp" &> /dev/null; then
        print_warning "aiohttp 未安裝，正在安裝..."
        pip3 install aiohttp
    fi
    
    print_info "開始壓力測試..."
    cd tests && python3 stress_test.py
}

# 函數：清理系統
clean_system() {
    print_header "清理系統"
    
    print_warning "這將刪除所有容器和資料卷（包含資料庫資料）"
    read -p "確定要繼續嗎？(y/N) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "停止並刪除所有容器..."
        docker-compose down -v
        
        print_info "清理未使用的 Docker 資源..."
        docker system prune -f
        
        print_success "清理完成"
    else
        print_info "已取消"
    fi
}

# 函數：查看統計資料
view_stats() {
    print_header "系統統計資料"
    
    print_info "查詢 API 統計..."
    curl -s http://localhost:8080/api/stats | python3 -m json.tool
}

# 函數：進入資料庫
enter_database() {
    print_header "連線到 PostgreSQL"
    
    print_info "進入資料庫（輸入 \\q 退出）"
    docker exec -it log-postgres psql -U loguser -d logsdb
}

# 函數：進入 Redis
enter_redis() {
    print_header "連線到 Redis"
    
    print_info "進入 Redis CLI（輸入 quit 退出）"
    docker exec -it log-redis redis-cli
}

# 函數：顯示使用說明
show_help() {
    print_header "日誌收集系統管理腳本"
    
    echo "用法: $0 [命令]"
    echo ""
    echo "可用命令："
    echo "  start         - 啟動系統"
    echo "  stop          - 停止系統"
    echo "  restart       - 重啟系統"
    echo "  status        - 檢查服務狀態"
    echo "  logs [服務]   - 查看日誌（可選擇特定服務）"
    echo "  test          - 執行壓力測試"
    echo "  stats         - 查看統計資料"
    echo "  db            - 進入 PostgreSQL"
    echo "  redis         - 進入 Redis CLI"
    echo "  clean         - 清理系統（刪除所有資料）"
    echo "  help          - 顯示此說明"
    echo ""
    echo "服務名稱："
    echo "  nginx         - Nginx 負載平衡器"
    echo "  fastapi-1     - FastAPI 實例 1"
    echo "  fastapi-2     - FastAPI 實例 2"
    echo "  worker        - 背景 Worker"
    echo "  postgres      - PostgreSQL 資料庫"
    echo "  redis         - Redis 快取"
    echo ""
    echo "範例："
    echo "  $0 start              # 啟動系統"
    echo "  $0 logs worker        # 查看 Worker 日誌"
    echo "  $0 test               # 執行壓力測試"
}

# ==========================================
# 主程式
# ==========================================

# 檢查參數
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# 執行命令
case "$1" in
    start)
        check_docker
        start_system
        ;;
    stop)
        stop_system
        ;;
    restart)
        check_docker
        restart_system
        ;;
    status)
        check_services
        ;;
    logs)
        view_logs "$2"
        ;;
    test)
        run_stress_test
        ;;
    stats)
        view_stats
        ;;
    db)
        enter_database
        ;;
    redis)
        enter_redis
        ;;
    clean)
        clean_system
        ;;
    help)
        show_help
        ;;
    *)
        print_error "未知命令: $1"
        show_help
        exit 1
        ;;
esac
