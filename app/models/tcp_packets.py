from __future__ import annotations

from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, Field


class RegisterPacket(BaseModel):
    """设备首次联网注册包。"""
    type: str = "register"
    device_id: Optional[str] = Field(default=None, alias="deviceId")
    imei: Optional[str] = None

    model_config = {"populate_by_name": True}

    def get_imei(self) -> Optional[str]:
        return self.imei or self.device_id


class GpsPacket(BaseModel):
    """高频定位简包，1 秒一次。"""
    lat: float
    lng: float
    speed: Optional[float] = None    # km/h
    altitude: Optional[float] = None


class FullStatePacket(BaseModel):
    """低频全量状态包（10~150 秒一次）。设备短字段：ic/q/vb/dt 与 Lua 全量包一致。"""
    imei: str
    report_time: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("reportTime", "dt"),
    )
    signal_strength: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("signalStrength", "q"),
    )
    iccid: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("iccid", "ic"),
    )
    battery_voltage: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("batteryVoltage", "vb"),
    )
    firmware_version: Optional[str] = Field(default=None, alias="firmwareVersion")
    gps: Optional[dict[str, Any]] = None
    lbs: Optional[dict[str, Any]] = None

    model_config = {"populate_by_name": True}

    def gps_lat(self) -> Optional[float]:
        if self.gps:
            v = self.gps.get("lat") or self.gps.get("la")
            return float(v) if v is not None else None
        return None

    def gps_lng(self) -> Optional[float]:
        if self.gps:
            v = self.gps.get("lng") or self.gps.get("ln")
            return float(v) if v is not None else None
        return None

    def gps_speed(self) -> Optional[float]:
        if self.gps:
            v = self.gps.get("speed") or self.gps.get("sp")
            return float(v) if v is not None else None
        return None

    def gps_altitude(self) -> Optional[float]:
        if self.gps:
            v = self.gps.get("altitude") or self.gps.get("al")
            return float(v) if v is not None else None
        return None

    def is_gps_fixed(self) -> bool:
        if not self.gps:
            return False
        v = self.gps.get("isFix") or self.gps.get("f") or self.gps.get("isFixed")
        return bool(v)

    def lbs_lat(self) -> Optional[float]:
        if self.lbs:
            v = self.lbs.get("lat") or self.lbs.get("la")
            return float(v) if v is not None else None
        return None

    def lbs_lng(self) -> Optional[float]:
        if self.lbs:
            v = self.lbs.get("lng") or self.lbs.get("ln")
            return float(v) if v is not None else None
        return None
