from enum import Enum


class WorkState(str, Enum):
    LOADING = "loading"
    UNLOADING = "unloading"
    TRANSPORT_LOADED = "transport_loaded"
    TRANSPORT_EMPTY = "transport_empty"
    UNKNOWN = "unknown"


class Command(str, Enum):
    GM = "gm"   # 早上欢迎语
    GA = "ga"   # 下午欢迎语
    GN = "gn"   # 晚上欢迎语
    WS = "ws"   # 超速提醒
    WA = "wa"   # 越界提醒
    VS = "vs"   # 车辆调度（会车/单边桥）


class UserRole(str, Enum):
    MANAGER = "manager"
    FLEET_CAPTAIN = "fleet_captain"
    TERMINAL = "terminal"


class EventType(str, Enum):
    OVERSPEED = "overspeed"
    GEOFENCE_VIOLATION = "geofence_violation"
    ONCOMING_WARN = "oncoming_warn"
    DISPATCH = "dispatch"
    BAN_VIOLATION = "ban_violation"
    ZONE_ENTRY = "zone_entry"
    ZONE_EXIT = "zone_exit"
    DEVICE_OFFLINE = "device_offline"
    UNREPORTED_EXIT = "unreported_exit"
    MANUAL_COMMAND = "manual_command"  # HTTP 手动下发指令


class ZoneType(str, Enum):
    LOADING = "loading"
    UNLOADING = "unloading"
    RESTRICTED = "restricted"
    SHARP_CURVE = "sharp_curve"
    SINGLE_BRIDGE = "single_bridge"
    SPEED_ZONE = "speed_zone"


class LocType(str, Enum):
    GPS = "gps"
    LBS = "lbs"
