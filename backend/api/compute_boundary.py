"""Java mode exposes computation to the authenticated gateway only."""
import os
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from .dataset_context import DatasetContextError, require_internal


class ComputeBoundaryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        protected = path == '/api' or path.startswith('/api/')
        if scope['type'] == 'http' and os.environ.get('TFIELD_MODEL_STORE_MODE', 'java').lower() != 'legacy' and protected and path != '/api/health':
            try:
                require_internal(Headers(scope=scope))
            except DatasetContextError as exc:
                await JSONResponse({'detail': exc.detail}, status_code=exc.status)(scope, receive, send)
                return
        await self.app(scope, receive, send)
