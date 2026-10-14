"""Cap public auth JSON before decoding; preserve CORS/error envelopes."""
from app.application.contracts.auth import AuthError


class AuthBodyLimits:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        auth_write = scope.get("method") == "POST" and scope.get("path", "").startswith("/api/v1/auth/")
        notification_write = scope.get("method") == "PATCH" and scope.get("path", "").startswith("/api/v1/notifications/")
        collaboration_write = scope.get("method") == "POST" and any(p in scope.get("path", "") for p in ('/permission-requests', '/mapping-submissions'))
        store_write = scope.get('method')=='POST' and scope.get('path')=='/api/v1/stores'
        if scope["type"] != "http" or not (auth_write or notification_write or collaboration_write or store_write):
            return await self.app(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > 65536:
                scope.setdefault("state", {})["auth_body_limit"] = True
                raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
            return message

        await self.app(scope, bounded_receive, send)
