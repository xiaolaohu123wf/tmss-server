from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from app.cache.session_repo import SessionData
from app.core.device_registry import device_registry
from app.core.exceptions import NotFoundError
from app.db.deps import get_db_conn
from app.db.repos.device_repo import DeviceRepo
from app.http.deps import require_fleet_or_above, require_manager
from app.http.response import ok
from app.models.http_event import BindRequest, DeviceCreate, DeviceResponse

router = APIRouter(prefix="/api/devices", tags=["devices"])
_repo = DeviceRepo()


@router.get("")
async def list_devices(
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    rows = await _repo.find_all(conn)
    return ok([DeviceResponse(
        id=r.id, imei=r.imei, iccid=r.iccid,
        model=r.model, firmware_version=r.firmware_version, notes=r.notes,
    ).model_dump() for r in rows])


@router.post("")
async def create_device(
    body: DeviceCreate,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    new_id = await _repo.create(
        conn, imei=body.imei, iccid=body.iccid,
        model=body.model, firmware_version=body.firmware_version, notes=body.notes,
    )
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
    # 先解绑旧绑定（如有）
    await _repo.unbind(conn, device_id)
    bind_id = await _repo.bind(
        conn, device_id, body.vehicle_id,
        driver_id=body.driver_id,
        operator=body.operator or session.username,
    )
    # 查询车辆所属车队，同步刷新在线设备的内存状态
    fleet_row = await conn.fetchrow(
        "SELECT fleet_id FROM vehicle WHERE id = $1 AND deleted_at IS NULL",
        body.vehicle_id,
    )
    fleet_id = fleet_row["fleet_id"] if fleet_row else None
    await device_registry.update_binding(device_id, body.vehicle_id, fleet_id)
    return ok({"bind_id": bind_id})


@router.post("/{device_id}/unbind")
async def unbind_device(
    device_id: int,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    await _repo.unbind(conn, device_id)
    # 同步清除在线设备的内存绑定状态
    await device_registry.update_binding(device_id, None, None)
    return ok({"message": "已解绑"})


@router.delete("/{device_id}")
async def delete_device(
    device_id: int,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    row = await _repo.find_by_id(conn, device_id)
    if row is None:
        raise NotFoundError("设备不存在")
    await _repo.soft_delete(conn, device_id)
    return ok({"message": "已删除"})
