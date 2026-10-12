"""Streaming request cap before import body decoding/spooling."""

from app.application.contracts.auth import AuthError


class ImportBodyLimits:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        relevant = (
            scope["type"] == "http"
            and scope.get("method") in {"POST", "PATCH"}
            and ("/imports" in path or "/mapping-profiles/" in path or "/recipe-schedule/changes" in path)
        )
        if not relevant:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", ()))
        multipart = headers.get(b"content-type", b"").startswith(
            b"multipart/form-data"
        ) and path.endswith("/files")
        limit = 100 * 1024 * 1024 + 128 * 1024 if multipart else 65536
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > limit:
                scope.setdefault("state", {})["import_resource_limit"] = True
                raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
            return message

        await self.app(scope, bounded_receive, send)
