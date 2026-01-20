"""Tenant middleware for multi-tenancy."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware to handle tenant context."""

    async def dispatch(self, request: Request, call_next):
        """Process request and add tenant context."""
        # Get tenant ID from header
        tenant_id = request.headers.get("X-Tenant-ID")

        # Store tenant_id in request state for later use
        request.state.tenant_id = tenant_id

        response: Response = await call_next(request)
        return response
