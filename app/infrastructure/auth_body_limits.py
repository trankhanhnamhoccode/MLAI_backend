"""Cap public auth JSON before decoding; preserve CORS/error envelopes."""
from app.application.contracts.auth import AuthError


class AuthBodyLimits:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or not scope.get("path", "").startswith("/api/v1/auth/"):
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
