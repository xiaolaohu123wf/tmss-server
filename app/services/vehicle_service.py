from __future__ import annotations

from decimal import Decimal
from typing import Optional

import asyncpg

from app.cache.session_repo import SessionData
from app.core.enums import UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.db.repos.vehicle_repo import VehicleRepo, VehicleRow
from app.models.http_vehicle import VehicleCreate, VehicleResponse, VehicleUpdate

_repo = VehicleRepo()


def _to_response(row: VehicleRow) -> VehicleResponse:
    return VehicleResponse(
        id=row.id,
        fleet_id=row.fleet_id,
        fleet_name=row.fleet_name,
        license_plate=row.license_plate,
        vehicle_type=row.vehicle_type,
        load_capacity=row.load_capacity,
        driver_name=row.driver_name,
        driver_phone=row.driver_phone,
        device_id=row.device_id,
        device_imei=row.device_imei,
        notes=row.notes,
    )


class VehicleService:
    async def list_vehicles(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        session: SessionData,
    ) -> list[VehicleResponse]:
        # manager 可查全部；fleet_captain 只查本车队
        rows = await _repo.find_active(conn, fleet_id=session.fleet_id)
        return [_to_response(r) for r in rows]

    async def get_vehicle(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        vehicle_id: int,
        session: SessionData,
    ) -> VehicleResponse:
        row = await _repo.find_by_id(conn, vehicle_id)
        if row is None:
            raise NotFoundError("车辆不存在")
        _check_fleet_access(row.fleet_id, session)
        return _to_response(row)

    async def create_vehicle(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        body: VehicleCreate,
        session: SessionData,
    ) -> VehicleResponse:
        # fleet_captain 只能创建本车队车辆
        fleet_id = body.fleet_id
        if session.role == UserRole.FLEET_CAPTAIN:
            fleet_id = session.fleet_id

        try:
            new_id = await _repo.create(
                conn,
                fleet_id=fleet_id,
                license_plate=body.license_plate,
                vehicle_type=body.vehicle_type,
                load_capacity=body.load_capacity,
                notes=body.notes,
                driver_name=body.driver_name,
                driver_phone=body.driver_phone,
            )
        except asyncpg.UniqueViolationError:
            raise ConflictError(f"车牌 {body.license_plate} 已存在")
        row = await _repo.find_by_id(conn, new_id)
        assert row is not None
        return _to_response(row)

    async def update_vehicle(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        vehicle_id: int,
        body: VehicleUpdate,
        session: SessionData,
    ) -> VehicleResponse:
        row = await _repo.find_by_id(conn, vehicle_id)
        if row is None:
            raise NotFoundError("车辆不存在")
        _check_fleet_access(row.fleet_id, session)

        try:
            await _repo.update(
                conn, vehicle_id,
                license_plate=body.license_plate,
                vehicle_type=body.vehicle_type,
                load_capacity=body.load_capacity,
                notes=body.notes,
                fleet_id=body.fleet_id if session.role == UserRole.MANAGER else None,
                driver_name=body.driver_name,
                driver_phone=body.driver_phone,
            )
        except asyncpg.UniqueViolationError:
            raise ConflictError(f"车牌 {body.license_plate} 已存在")
        updated = await _repo.find_by_id(conn, vehicle_id)
        assert updated is not None
        return _to_response(updated)

    async def delete_vehicle(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        vehicle_id: int,
        session: SessionData,
    ) -> None:
        row = await _repo.find_by_id(conn, vehicle_id)
        if row is None:
            raise NotFoundError("车辆不存在")
        _check_fleet_access(row.fleet_id, session)
        await _repo.soft_delete(conn, vehicle_id)


def _check_fleet_access(fleet_id: Optional[int], session: SessionData) -> None:
    """fleet_captain 只能访问本车队数据。"""
    if session.role == UserRole.FLEET_CAPTAIN and fleet_id != session.fleet_id:
        raise PermissionDeniedError("无权访问其他车队数据")
