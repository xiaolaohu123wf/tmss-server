from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Query

from datetime import datetime, timezone
from typing import Optional

from app.cache.session_repo import SessionData
from app.core.device_registry import device_registry
from app.core.enums import Command, EventType, UserRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.db.deps import get_db_conn
from app.db.repos.device_repo import DeviceRepo
from app.db.repos.event_repo import EventRepo
from app.http.deps import require_fleet_or_above, require_manager
from app.http.response import ok
from app.models.http_event import (
    BindRequest,
    CommandRequest,
    DeviceCreate,
    DeviceMetadataUpdate,
    DeviceResponse,
)
from app.services.command_service import send as send_command_to_device

router = APIRouter(prefix="/api/devices", tags=["devices"])
_repo = DeviceRepo()
_event_repo = EventRepo()


@router.get("")
async def list_devices(
    unbound: Optional[bool] = Query(default=None, description="仅返回未绑定车辆的设备"),
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    if unbound:
        rows = await _repo.find_unbound(conn)
    else:
        rows = await _repo.find_all(conn)

    device_ids = [r.id for r in rows]
    locs = await _repo.latest_locations(conn, device_ids)
    loc_map = {lp.device_id: lp for lp in locs}

    online_states = await device_registry.list_online()
    online_map = {s.device_id: s for s in online_states}

    result = []
    for r in rows:
        loc = loc_map.get(r.id)
        state = online_map.get(r.id)
        result.append(DeviceResponse(
            id=r.id, imei=r.imei, iccid=r.iccid,
            model=r.model, firmware_version=r.firmware_version, notes=r.notes,
            vehicle_id=r.vehicle_id,
            vehicle_license=r.vehicle_license,
            fleet_id=r.fleet_id,
            online=state is not None,
            last_heartbeat_at=state.last_heartbeat_at.isoformat() if state else None,
            last_loc_type=loc.loc_type if loc else None,
            last_lat=loc.lat if loc else None,
            last_lng=loc.lng if loc else None,
            last_location_at=loc.recorded_at.isoformat() if loc else None,
        ).model_dump())
    return ok(result)


@router.post("")
async def create_device(
    body: DeviceCreate,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    try:
        new_id = await _repo.create(
            conn, imei=body.imei, iccid=body.iccid,
            model=body.model, firmware_version=body.firmware_version, notes=body.notes,
        )
    except asyncpg.UniqueViolationError:
        raise ConflictError(f"IMEI {body.imei} 已存在且处于活跃状态，请勿重复添加")
    row = await _repo.find_by_id(conn, new_id)
    assert row is not None
    return ok(DeviceResponse(
        id=row.id, imei=row.imei, iccid=row.iccid,
        model=row.model, firmware_version=row.firmware_version, notes=row.notes,
    ).model_dump())


@router.post("/{device_id}/bind")
async def bind_device(
    device_id: int,
    body: BindRequest,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    # 车队长只能把设备绑定到本车队的车辆
    if session.role == UserRole.FLEET_CAPTAIN:
        vehicle_row = await conn.fetchrow(
            "SELECT fleet_id FROM vehicle WHERE id = $1 AND deleted_at IS NULL",
            body.vehicle_id,
        )
        if vehicle_row is None:
            raise NotFoundError("车辆不存在")
        if vehicle_row["fleet_id"] != session.fleet_id:
            raise PermissionDeniedError("只能绑定本车队的车辆")

    await _repo.unbind(conn, device_id)
    bind_id = await _repo.bind(
        conn, device_id, body.vehicle_id,
        driver_id=body.driver_id,
        operator=body.operator or session.username,
    )
    fleet_row = await conn.fetchrow(
        "SELECT fleet_id, license_plate FROM vehicle WHERE id = $1 AND deleted_at IS NULL",
        body.vehicle_id,
    )
    fleet_id = fleet_row["fleet_id"] if fleet_row else None
    license_plate = fleet_row["license_plate"] if fleet_row else None
    await device_registry.update_binding(device_id, body.vehicle_id, fleet_id, license_plate)
    return ok({"bind_id": bind_id})


@router.post("/{device_id}/unbind")
async def unbind_device(
    device_id: int,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    # 车队长只能解绑本车队的设备
    if session.role == UserRole.FLEET_CAPTAIN:
        bind = await _repo.get_active_bind_by_device(conn, device_id)
        if bind is None:
            raise NotFoundError("设备当前未绑定")
        vehicle_row = await conn.fetchrow(
            "SELECT fleet_id FROM vehicle WHERE id = $1 AND deleted_at IS NULL",
            bind.vehicle_id,
        )
        if vehicle_row is None or vehicle_row["fleet_id"] != session.fleet_id:
            raise PermissionDeniedError("只能解绑本车队的设备")

    await _repo.unbind(conn, device_id)
    await device_registry.update_binding(device_id, None, None)
    return ok({"message": "已解绑"})


@router.post("/{device_id}/command")
async def send_command(
    device_id: int,
    body: CommandRequest,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    # Validate command value
    try:
        cmd = Command(body.command)
    except ValueError:
        valid = [c.value for c in Command]
        raise NotFoundError(f"未知指令 '{body.command}'，有效指令：{valid}")

    # Get device info for context
    row = await _repo.find_by_id(conn, device_id)
    if row is None:
        raise NotFoundError("设备不存在")

    locs = await _repo.latest_locations(conn, [device_id])
    speed_kmh = locs[0].speed if locs else None

    delivered = await send_command_to_device(
        device_id=device_id,
        cmd=cmd,
        registry=device_registry,
        conn=conn,
        vehicle_id=row.vehicle_id,
        source="manual",
        operator_id=session.user_id,
        speed_kmh=speed_kmh,
    )

    loc = locs[0] if locs else None
    await _event_repo.insert(
        conn,
        event_type=EventType.MANUAL_COMMAND,
        occurred_at=datetime.now(tz=timezone.utc),
        device_id=device_id,
        vehicle_id=row.vehicle_id,
        severity=1,
        lat=loc.lat if loc else None,
        lng=loc.lng if loc else None,
        speed=speed_kmh,
        cmd_sent=cmd.value,
        detail={
            "source": "manual",
            "command": cmd.value,
            "delivered": delivered,
            "operator_id": session.user_id,
        },
    )

    return ok({
        "delivered": delivered,
        "message": "指令已下发" if delivered else "设备不在线，指令已记录但未送达",
        "speed_kmh_recorded": speed_kmh,
    })


@router.put("/{device_id}")
async def update_device_metadata(
    device_id: int,
    body: DeviceMetadataUpdate,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    row = await _repo.find_by_id(conn, device_id)
    if row is None:
        raise NotFoundError("设备不存在")
    await _repo.update_metadata(
        conn,
        device_id,
        iccid=body.iccid.strip() or None,
    )
    return ok({"message": "设备信息已更新"})


@router.delete("/{device_id}")
async def delete_device(
    device_id: int,
    _session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    row = await _repo.find_by_id(conn, device_id)
    if row is None:
        raise NotFoundError("设备不存在")
    await _repo.unbind(conn, device_id)
    await device_registry.update_binding(device_id, None, None)
    await device_registry.unregister(device_id)
    await _repo.soft_delete(conn, device_id)
    return ok({"message": "已删除"})
