from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class EventResponse(BaseModel):
    id: int
    device_id: Optional[int]
    vehicle_id: Optional[int]
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


class DeviceCreate(BaseModel):
    imei: str
    iccid: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    notes: Optional[str] = None


class BindRequest(BaseModel):
    vehicle_id: int
    driver_id: Optional[int] = None
    operator: Optional[str] = None
