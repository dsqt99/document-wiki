"""Header vai trò do bên gọi tự khai chỉ được tin khi cấu hình cho phép (mặc định tắt)."""

from app.config import settings
from app.mcp.tools import forwarded_role


def test_forged_admin_header_is_ignored_by_default():
    assert settings.mcp_trust_forwarded_identity is False
    assert forwarded_role({"x-user-role": "admin"}, settings.mcp_trust_forwarded_identity) == ""


def test_header_is_honoured_only_when_explicitly_trusted():
    assert forwarded_role({"x-user-role": " Admin "}, True) == "admin"
    assert forwarded_role({}, True) == ""
