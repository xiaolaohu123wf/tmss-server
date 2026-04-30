from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


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


class DeviceMetadataUpdate(BaseModel):
    """设备管理页编辑固件、ICCID"""
    firmware_version: str = ""
    iccid: str = ""


class CommandRequest(BaseModel):
    command: str  # must match a Command enum value


class BindRequest(BaseModel):
    vehicle_id: int
    driver_id: Optional[int] = None
    operator: Optional[str] = None
