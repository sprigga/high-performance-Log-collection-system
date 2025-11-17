# 專案結構說明

```
log-collection-system/
│
├── docker-compose.yml          # Docker Compose 主配置檔（核心功能版）
├── .env.example                # 環境變數範例檔
├── manage.sh                   # 系統管理腳本（啟動、停止、監控）
├── README.md                   # 完整的使用說明文件
├── QUICKSTART.md               # 快速開始指南
│
├── nginx/                      # Nginx 負載平衡器配置
│   └── nginx.conf              # Nginx 配置檔
│
├── app/                        # 應用程式程式碼
│   ├── Dockerfile              # FastAPI 容器映像檔
│   ├── requirements.txt        # Python 依賴套件
│   ├── main.py                 # FastAPI 主應用程式（API 端點）
│   ├── models.py               # 資料模型定義（Pydantic & SQLAlchemy）
│   ├── database.py             # 資料庫連線配置（連線池）
│   └── worker.py               # 背景工作程序（從 Redis 消費日誌）
│
├── postgres/                   # PostgreSQL 配置
│   └── init.sql                # 資料庫初始化 SQL 腳本
│
└── tests/                      # 測試腳本
    └── stress_test.py          # 壓力測試腳本（模擬 100 台設備）
```

## 📁 檔案說明

### 根目錄檔案

- **docker-compose.yml**: Docker Compose 編排檔案，定義所有服務（Nginx、FastAPI、Worker、Redis、PostgreSQL）
- **.env.example**: 環境變數範例，可複製為 `.env` 並修改
- **manage.sh**: 便利的管理腳本，提供啟動、停止、查看日誌等功能
- **README.md**: 完整的專案說明文件
- **QUICKSTART.md**: 10 分鐘快速開始指南

### nginx/ 目錄

- **nginx.conf**: Nginx 負載平衡器的完整配置
  - Upstream 後端服務定義
  - 負載平衡演算法（least_conn）
  - 限流配置
  - 健康檢查端點
  - 連線保持設定

### app/ 目錄

應用程式的核心程式碼，包含：

- **Dockerfile**: 定義 FastAPI 應用程式的容器映像檔
  - 基於 Python 3.11
  - 安裝所有依賴
  - 配置工作目錄

- **requirements.txt**: Python 依賴套件清單
  - FastAPI: Web 框架
  - SQLAlchemy: ORM 和資料庫連線池
  - Redis: 快取和訊息佇列客戶端
  - 其他工具套件

- **main.py**: FastAPI 主應用程式 (~300 行)
  - API 端點定義
  - 健康檢查
  - 日誌寫入（Redis Stream）
  - 日誌查詢（快取優先）
  - 統計資料

- **models.py**: 資料模型定義 (~200 行)
  - SQLAlchemy ORM 模型（資料庫表格）
  - Pydantic 模型（API 請求/回應）
  - 資料驗證

- **database.py**: 資料庫連線管理 (~150 行)
  - 同步/非同步引擎配置
  - 連線池設定
  - Session 管理
  - 依賴注入函數

- **worker.py**: 背景工作程序 (~250 行)
  - 從 Redis Stream 消費日誌
  - 批次寫入 PostgreSQL
  - 錯誤處理和重試
  - 優雅關閉

### postgres/ 目錄

- **init.sql**: 資料庫初始化腳本
  - 建立 `logs` 主表
  - 建立索引（單一索引、複合索引、GIN 索引）
  - 建立輔助表格（devices、log_statistics）
  - 建立視圖和函數
  - 插入範例資料

### tests/ 目錄

- **stress_test.py**: 壓力測試腳本 (~400 行)
  - 模擬 100 台設備併發發送日誌
  - 詳細的效能統計
  - 回應時間百分位數（P50、P95、P99）
  - 錯誤分析

## 🎯 關鍵技術點

### 1. 負載平衡（Nginx）
- 使用 `least_conn` 演算法分散請求
- 設定連線保持（keepalive）減少 TCP 握手
- 實作限流保護系統

### 2. 非同步處理（FastAPI + Redis）
- API 快速回應（< 5ms）
- 將日誌寫入 Redis Stream 後立即返回
- 背景 Worker 非同步處理

### 3. 批次優化（Worker）
- 批次讀取 100 筆日誌
- 批次寫入資料庫
- 減少資料庫操作次數

### 4. 連線池（SQLAlchemy）
- 避免頻繁建立/關閉連線
- 複用連線提升效能
- 自動管理連線生命週期

### 5. 智慧快取（Redis）
- 查詢結果快取（TTL 5 分鐘）
- 減少資料庫查詢壓力
- LRU 淘汰策略

### 6. 資料持久化
- PostgreSQL 資料儲存
- Redis AOF 持久化
- Docker Volume 資料卷

## 📊 資料流程

```
寫入流程：
設備 → Nginx → FastAPI → Redis Stream → Worker → PostgreSQL
              ↓
         立即回應 (2-3ms)

讀取流程：
客戶端 → Nginx → FastAPI → Redis Cache?
                             ↓ Miss
                        PostgreSQL
                             ↓
                        寫入 Cache → 返回
```

## 🔧 可擴展性

系統設計支援水平擴展：

1. **FastAPI 實例**: 可增加到 3、5、10 個
2. **Worker**: 可增加處理更多日誌
3. **Redis**: 可升級到 Cluster 模式
4. **PostgreSQL**: 可配置主備架構

只需修改 `docker-compose.yml` 即可擴展！

## 📦 部署方式

1. **本機開發**: `docker-compose up -d`
2. **雲端部署**: 支援任何支援 Docker 的平台
3. **Kubernetes**: 可轉換為 K8s 配置
4. **生產環境**: 加入監控、日誌聚合等功能

## 🎓 學習路徑

建議的學習順序：

1. 先看 `QUICKSTART.md` 快速部署系統
2. 閱讀 `README.md` 了解完整功能
3. 查看 `main.py` 理解 API 實作
4. 研究 `worker.py` 了解批次處理
5. 分析 `database.py` 學習連線池
6. 執行 `stress_test.py` 測試效能
7. 修改配置調優系統

## 💡 最佳實踐

這個專案展示了以下最佳實踐：

- ✅ 容器化部署（Docker）
- ✅ 服務編排（Docker Compose）
- ✅ 負載平衡（Nginx）
- ✅ 非同步處理（FastAPI async）
- ✅ 訊息佇列（Redis Stream）
- ✅ 批次優化（Batch Processing）
- ✅ 連線池管理（SQLAlchemy）
- ✅ 智慧快取（Redis Cache）
- ✅ 健康檢查（Health Check）
- ✅ 優雅關閉（Graceful Shutdown）
- ✅ 錯誤處理（Error Handling）
- ✅ 日誌記錄（Logging）
- ✅ API 文件（OpenAPI/Swagger）
- ✅ 壓力測試（Performance Testing）

希望這個專案對你的學習有幫助！🚀
