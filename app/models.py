"""
資料模型定義
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Index
from sqlalchemy.sql import func
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from database import Base

# ==========================================
# SQLAlchemy ORM 模型
# ==========================================
class Log(Base):
    """
    日誌資料表
    """
    __tablename__ = 'logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(50), nullable=False, index=True)
    log_level = Column(String(20), nullable=False, index=True)
    message = Column(Text, nullable=True)
    log_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    indexed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # 複合索引（常用查詢模式）
    __table_args__ = (
        Index('idx_device_created', 'device_id', 'created_at'),
        Index('idx_created_desc', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Log(id={self.id}, device={self.device_id}, level={self.log_level})>"

# ==========================================
# Pydantic 模型（API 請求/回應）
# ==========================================
class LogEntryRequest(BaseModel):
    """
    建立日誌請求模型
    """
    device_id: str = Field(..., min_length=1, max_length=50, description="設備ID")
    log_level: str = Field(..., description="日誌等級 (DEBUG/INFO/WARNING/ERROR/CRITICAL)")
    message: str = Field(..., min_length=1, max_length=5000, description="日誌訊息")
    log_data: Optional[Dict[str, Any]] = Field(default={}, description="額外的 JSON 資料")
    
    class Config:
        json_schema_extra = {
            "example": {
                "device_id": "device_001",
                "log_level": "ERROR",
                "message": "Database connection failed",
                "log_data": {
                    "error_code": "DB_CONN_001",
                    "retry_count": 3,
                    "timestamp": "2024-11-14T10:30:00Z"
                }
            }
        }

class LogEntryResponse(BaseModel):
    """
    日誌建立回應模型
    """
    status: str = Field(default="queued", description="狀態")
    message_id: str = Field(..., description="訊息ID（Redis Stream ID）")
    received_at: datetime = Field(default_factory=datetime.now, description="接收時間")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "queued",
                "message_id": "1699960200000-0",
                "received_at": "2024-11-14T10:30:00.123456"
            }
        }

# 批量日誌請求模型（新增）
class BatchLogEntryRequest(BaseModel):
    """
    批量建立日誌請求模型
    """
    logs: list[LogEntryRequest] = Field(..., min_length=1, max_length=1000, description="日誌列表")

    class Config:
        json_schema_extra = {
            "example": {
                "logs": [
                    {
                        "device_id": "device_001",
                        "log_level": "ERROR",
                        "message": "Database connection failed",
                        "log_data": {"error_code": "DB_CONN_001"}
                    }
                ]
            }
        }

class BatchLogEntryResponse(BaseModel):
    """
    批量日誌建立回應模型
    """
    status: str = Field(default="queued", description="狀態")
    count: int = Field(..., description="接收的日誌數量")
    message_ids: list[str] = Field(..., description="訊息ID列表")
    received_at: datetime = Field(default_factory=datetime.now, description="接收時間")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "queued",
                "count": 100,
                "message_ids": ["1699960200000-0", "1699960200000-1"],
                "received_at": "2024-11-14T10:30:00.123456"
            }
        }

class LogQueryResponse(BaseModel):
    """
    日誌查詢回應模型
    """
    id: int
    device_id: str
    log_level: str
    message: str
    log_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "device_id": "device_001",
                "log_level": "ERROR",
                "message": "Database connection failed",
                "log_data": {"error_code": "DB_CONN_001"},
                "created_at": "2024-11-14T10:30:00"
            }
        }

class BatchLogQueryResponse(BaseModel):
    """
    批次查詢回應模型
    """
    total: int = Field(..., description="總筆數")
    source: str = Field(..., description="資料來源 (cache/database)")
    data: list[LogQueryResponse]
    
    class Config:
        json_schema_extra = {
            "example": {
                "total": 100,
                "source": "cache",
                "data": [
                    {
                        "id": 1,
                        "device_id": "device_001",
                        "log_level": "ERROR",
                        "message": "Database connection failed",
                        "log_data": {},
                        "created_at": "2024-11-14T10:30:00"
                    }
                ]
            }
        }

class HealthCheckResponse(BaseModel):
    """
    健康檢查回應模型
    """
    status: str = Field(..., description="健康狀態")
    instance: str = Field(..., description="實例名稱")
    checks: Dict[str, bool] = Field(..., description="各組件檢查結果")
    timestamp: datetime = Field(default_factory=datetime.now, description="檢查時間")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "instance": "fastapi-1",
                "checks": {
                    "redis": True,
                    "postgres": True
                },
                "timestamp": "2024-11-14T10:30:00"
            }
        }

class StatsResponse(BaseModel):
    """
    統計資料回應模型
    """
    total_logs: int = Field(..., description="總日誌數")
    logs_by_level: Dict[str, int] = Field(..., description="按等級統計")
    recent_devices: list[str] = Field(..., description="最近活躍的設備")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_logs": 1000000,
                "logs_by_level": {
                    "DEBUG": 500000,
                    "INFO": 300000,
                    "WARNING": 150000,
                    "ERROR": 50000
                },
                "recent_devices": ["device_001", "device_002"]
            }
        }
