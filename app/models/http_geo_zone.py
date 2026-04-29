from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.enums import ZoneType


class GeoZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    zone_type: ZoneType
    coordinates: list[list[float]] = Field(min_length=3)
    speed_limit: Optional[int] = Field(default=None, ge=1, le=200)
    dwell_min: Optional[int] = Field(default=None, ge=1)
    is_enabled: bool = True
    notes: Optional[str] = None


class GeoZoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    zone_type: Optional[ZoneType] = None
    coordinates: Optional[list[list[float]]] = None
    speed_limit: Optional[int] = Field(default=None, ge=1, le=200)
    dwell_min: Optional[int] = Field(default=None, ge=1)
    is_enabled: Optional[bool] = None
    notes: Optional[str] = None


class GeoZoneResponse(BaseModel):
    id: int
    name: str
    zone_type: str
    coordinates: list[list[float]]
    speed_limit: Optional[int]
    dwell_min: Optional[int]
    is_enabled: bool
    extra: Optional[dict[str, Any]]
    notes: Optional[str]
