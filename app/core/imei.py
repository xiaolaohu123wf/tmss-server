"""设备 IMEI 规范化（与 TCP 注册逻辑一致，供 HTTP 人工录入共用）"""


def normalize_device_imei(raw: str) -> str:
    """纯数字 14 位时前补 0 → 15 位，与模块出厂号一致；含非数字则仅 strip。"""
    s = raw.strip()
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 14:
        return "0" + digits
    if len(digits) == 15:
        return digits
    return s
