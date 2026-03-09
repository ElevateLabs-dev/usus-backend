from fastapi import FastAPI
from starlette_admin.contrib.sqla import Admin

from src.admin.auth import AdminAuthProvider
from src.admin.views import TenantAdminView
from src.core.config import settings
from src.core.database import engine
from src.domains.tenants.models import Tenant


def setup_admin(app: FastAPI) -> None:
    """
    Mount the Starlette-Admin panel onto the FastAPI app at /admin.

    Called from create_app() in main.py after all routers are registered.
    """
    admin = Admin(
        engine,
        title="Usus Admin",
        auth_provider=AdminAuthProvider(),
        # itsdangerous session backed by SECRET_KEY
        middlewares=[],
    )

    # Register views
    admin.add_view(TenantAdminView(Tenant, label="Tenants"))

    admin.mount_to(app)
