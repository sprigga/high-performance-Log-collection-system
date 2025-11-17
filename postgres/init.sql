-- ==========================================
-- 日誌收集系統 - 資料庫初始化腳本
-- ==========================================

-- 建立主要的日誌表
CREATE TABLE IF NOT EXISTS logs (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL,
    log_level VARCHAR(20) NOT NULL,
    message TEXT,
    log_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    indexed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 建立索引（優化查詢效能）
-- 複合索引：設備ID + 建立時間（最常用的查詢模式）
CREATE INDEX IF NOT EXISTS idx_device_created 
ON logs(device_id, created_at DESC);

-- 單一索引：日誌等級
CREATE INDEX IF NOT EXISTS idx_log_level 
ON logs(log_level);

-- 單一索引：建立時間（降序）
CREATE INDEX IF NOT EXISTS idx_created_at 
ON logs(created_at DESC);

-- GIN 索引：JSONB 欄位（用於 JSON 查詢）
CREATE INDEX IF NOT EXISTS idx_log_data_gin 
ON logs USING GIN(log_data);

-- ==========================================
-- 設備資訊表（可選）
-- ==========================================
CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) UNIQUE NOT NULL,
    device_name VARCHAR(100),
    device_type VARCHAR(50),
    status VARCHAR(20) DEFAULT 'active',
    last_active TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);

-- 設備索引
CREATE INDEX IF NOT EXISTS idx_device_status 
ON devices(status);

CREATE INDEX IF NOT EXISTS idx_device_last_active 
ON devices(last_active DESC);

-- ==========================================
-- 日誌統計表（可選）
-- ==========================================
CREATE TABLE IF NOT EXISTS log_statistics (
    id SERIAL PRIMARY KEY,
    stat_date DATE NOT NULL,
    device_id VARCHAR(50),
    total_logs INTEGER DEFAULT 0,
    error_logs INTEGER DEFAULT 0,
    warning_logs INTEGER DEFAULT 0,
    info_logs INTEGER DEFAULT 0,
    debug_logs INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(stat_date, device_id)
);

-- 統計表索引
CREATE INDEX IF NOT EXISTS idx_stat_date 
ON log_statistics(stat_date DESC);

CREATE INDEX IF NOT EXISTS idx_stat_device 
ON log_statistics(device_id);

-- ==========================================
-- 視圖：每日日誌摘要
-- ==========================================
CREATE OR REPLACE VIEW daily_log_summary AS
SELECT 
    DATE(created_at) as log_date,
    device_id,
    log_level,
    COUNT(*) as log_count,
    MIN(created_at) as first_log,
    MAX(created_at) as last_log
FROM logs
GROUP BY DATE(created_at), device_id, log_level
ORDER BY log_date DESC, device_id;

-- ==========================================
-- 函數：自動更新 indexed_at 欄位
-- ==========================================
CREATE OR REPLACE FUNCTION update_indexed_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.indexed_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 觸發器：更新時自動設定 indexed_at
CREATE TRIGGER trigger_update_indexed_at
BEFORE UPDATE ON logs
FOR EACH ROW
EXECUTE FUNCTION update_indexed_at();

-- ==========================================
-- 函數：清理舊日誌（保留最近 30 天）
-- ==========================================
CREATE OR REPLACE FUNCTION cleanup_old_logs(days_to_keep INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM logs
    WHERE created_at < NOW() - (days_to_keep || ' days')::INTERVAL;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ==========================================
-- 範例資料（測試用）
-- ==========================================
-- 插入測試設備
INSERT INTO devices (device_id, device_name, device_type, status)
VALUES 
    ('device_001', '測試設備 001', 'sensor', 'active'),
    ('device_002', '測試設備 002', 'camera', 'active'),
    ('device_003', '測試設備 003', 'controller', 'inactive')
ON CONFLICT (device_id) DO NOTHING;

-- 插入測試日誌
INSERT INTO logs (device_id, log_level, message, log_data)
VALUES 
    ('device_001', 'INFO', '系統啟動', '{"version": "1.0.0", "boot_time": 1.2}'::jsonb),
    ('device_001', 'WARNING', '記憶體使用率偏高', '{"memory_usage": 85, "threshold": 80}'::jsonb),
    ('device_002', 'ERROR', '攝影機連線失敗', '{"error_code": "CAM_CONN_001", "retry_count": 3}'::jsonb),
    ('device_003', 'DEBUG', '偵錯訊息', '{"debug_level": 2, "module": "core"}'::jsonb)
ON CONFLICT DO NOTHING;

-- ==========================================
-- 授權設定
-- ==========================================
-- 確保應用程式使用者有正確的權限
GRANT ALL PRIVILEGES ON TABLE logs TO loguser;
GRANT ALL PRIVILEGES ON TABLE devices TO loguser;
GRANT ALL PRIVILEGES ON TABLE log_statistics TO loguser;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO loguser;

-- ==========================================
-- 完成訊息
-- ==========================================
DO $$
BEGIN
    RAISE NOTICE '✅ 資料庫初始化完成！';
    RAISE NOTICE '📊 已建立表格: logs, devices, log_statistics';
    RAISE NOTICE '🔍 已建立索引和視圖';
    RAISE NOTICE '🔧 已建立維護函數';
END $$;
