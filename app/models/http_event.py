from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, field_validator, model_validator


class EventResponse(BaseModel):
    id: int
    device_id: Optional[int]
    vehicle_id: Optional[int]
    vehicle_license: Optional[str] = None
    event_type: str
    severity: int
    zone_id: Optional[int]
    lat: Optional[float]
    lng: Optional[float]
    speed: Optional[float]
    cmd_sent: Optional[str]
    detail: Optional[dict[str, Any]]
    occurred_at: datetime


class EventListResponse(BaseModel):
    total: int
    items: list[EventResponse]


class DeviceResponse(BaseModel):
    id: int
    imei: str
    iccid: Optional[str]
    model: Optional[str]
    firmware_version: Optional[str]
    notes: Optional[str]
    # binding
    vehicle_id: Optional[int] = None
    vehicle_license: Optional[str] = None
    fleet_id: Optional[int] = None
    # runtime (from device_registry)
    online: bool = False
    last_heartbeat_at: Optional[str] = None
    # latest location (from DB)
    last_loc_type: Optional[str] = None   # 'gps' | 'lbs' | None
    last_lat: Optional[float] = None
    last_lng: Optional[float] = None
    last_location_at: Optional[str] = None


class DeviceCreate(BaseModel):
    imei: str
    iccid: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    notes: Optional[str] = None

    @field_validator('imei', mode='before')
    @classmethod
    def _normalize_imei(cls, v: object) -> str:
        from app.core.imei import normalize_device_imei

        if v is None:
            return ''
        return normalize_device_imei(str(v))

    @model_validator(mode='after')
    def _imei_must_be_valid(self) -> DeviceCreate:
        s = self.imei.strip()
        if len(s) != 15 or not s.isdigit():
            raise ValueError('IMEI 须为 15 位数字（14 位模块号请前补 0 或由系统自动补全）')
        return self


class DeviceMetadataUpdate(BaseModel):
    """设备管理页编辑 ICCID（固件版本由设备开机上报，不允许手动修改）"""
    iccid: str = ""


class CommandRequest(BaseModel):
    command: str  # must match a Command enum value


class BindRequest(BaseModel):
    vehicle_id: int
    driver_id: Optional[int] = None
    operator: Optional[str] = None
