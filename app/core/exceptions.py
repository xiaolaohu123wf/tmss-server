from __future__ import annotations


class TmssError(Exception):
    """业务异常基类。所有自定义异常必须继承此类。"""

    code: str = "tmss_error"
    http_status: int = 500
    message: str = "内部错误"

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class ProtocolError(TmssError):
    """TCP 报文解析失败。"""

    code = "protocol_error"
    http_status = 400
    message = "报文格式错误"


class NotFoundError(TmssError):
    """资源不存在。"""

    code = "not_found"
    http_status = 404
    message = "资源不存在"


class PermissionDeniedError(TmssError):
    """权限不足或越权访问其他车队数据。"""

    code = "permission_denied"
    http_status = 403
    message = "权限不足"


class ValidationError(TmssError):
    """业务规则校验失败（区别于 Pydantic 字段校验）。"""

    code = "validation_error"
    http_status = 422
    message = "业务校验失败"


class ExternalServiceError(TmssError):
    """外部服务调用失败（天气 API 等）。"""

    code = "external_service_error"
    http_status = 502
    message = "外部服务异常"
