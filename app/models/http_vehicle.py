from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class VehicleCreate(BaseModel):
    license_plate: str = Field(min_length=1, max_length=20)
    vehicle_type: str = Field(default="", max_length=30)
    load_capacity: Optional[Decimal] = None
    fleet_id: Optional[int] = None
    driver_name: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None


class VehicleUpdate(BaseModel):
    license_plate: Optional[str] = Field(default=None, max_length=20)
    vehicle_type: Optional[str] = Field(default=None, max_length=30)
    load_capacity: Optional[Decimal] = None
    fleet_id: Optional[int] = None
    driver_name: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None


class VehicleResponse(BaseModel):
    id: int
    fleet_id: Optional[int]
    fleet_name: Optional[str] = None
    license_plate: str
    vehicle_type: str
    load_capacity: Optional[Decimal]
    driver_name: Optional[str] = None
    device_id: Optional[int] = None
    device_imei: Optional[str] = None
    notes: Optional[str]
