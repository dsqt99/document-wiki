"""Giới hạn dung lượng yêu cầu tải lên ở tầng ASGI, trước khi framework nhận hết thân yêu cầu vào đĩa.

Starlette đọc trọn multipart vào tệp tạm trước khi gọi endpoint, nên kiểm tra trong endpoint không ngăn được một yêu
cầu vài GB làm đầy đĩa. Middleware này từ chối ngay theo `Content-Length` và đếm byte thực tế khi gửi dạng chunked.
"""

import json
from typing import Callable, Optional

# Phần bao multipart (ranh giới, tiêu đề, các trường form) cộng thêm vào dung lượng tệp.
MULTIPART_OVERHEAD = 1024 * 1024


class UploadSizeLimitMiddleware:
    def __init__(self, app, limit_for: Callable[[str, str], Optional[int]], on_reject: Optional[Callable] = None) -> None:
        """`limit_for(method, path)` trả về giới hạn byte của tệp, hoặc None nếu đường dẫn không bị giới hạn."""
        self.app = app
        self.limit_for = limit_for
        self.on_reject = on_reject

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        file_limit = self.limit_for(scope.get("method", ""), scope.get("path", ""))
        if not file_limit:
            await self.app(scope, receive, send)
            return

        limit = file_limit + MULTIPART_OVERHEAD
        declared = None
        for key, value in scope.get("headers", []):
            if key == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = None
                break

        if declared is not None and declared > limit:
            await self._reject(scope, send, file_limit, declared)
            return

        received = 0
        rejected = False

        async def counting_receive():
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    rejected = True
                    # Ngừng cấp dữ liệu: bộ phân tích multipart gặp yêu cầu bị ngắt và dừng đọc.
                    return {"type": "http.disconnect"}
            return message

        responded = False

        async def guarded_send(message) -> None:
            nonlocal responded
            if rejected:
                return  # đầu ra của endpoint bị cắt giữa chừng; trả 413 thay thế
            responded = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            if not rejected:
                raise
        if rejected and not responded:
            await self._reject(scope, send, file_limit, received)

    async def _reject(self, scope, send, file_limit: int, size: int) -> None:
        if self.on_reject:
            try:
                await self.on_reject(scope, file_limit, size)
            except Exception:
                pass
        body = json.dumps(
            {"detail": f"File tải lên vượt quá giới hạn dung lượng ({file_limit // (1024 * 1024)}MB)."}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})
