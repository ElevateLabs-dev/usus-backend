from fastapi import FastAPI
from starlette_admin.contrib.sqla import Admin

from src.admin.auth import AdminAuthProvider
from src.core.database import engine
from src.domains.evaluations.admin import (
    DimensionScoreAdminView,
    EvaluationResultAdminView,
    RedFlagAdminView,
)
from src.domains.evaluations.models import DimensionScore, EvaluationResult, RedFlag
from src.domains.scenarios.admin import ScenarioAdminView
from src.domains.scenarios.models import Scenario
from src.domains.simulations.admin import MessageAdminView, SessionAdminView
from src.domains.simulations.models import Message, Session
from src.domains.tenants.admin import TenantAdminView
from src.domains.tenants.models import Tenant
from src.domains.users.admin import UserAdminView
from src.domains.users.models import User


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
    admin.add_view(UserAdminView(User, label="Users"))
    admin.add_view(ScenarioAdminView(Scenario, label="Scenarios"))
    admin.add_view(SessionAdminView(Session, label="Sessions"))
    admin.add_view(MessageAdminView(Message, label="Messages"))
    admin.add_view(
        EvaluationResultAdminView(EvaluationResult, label="Evaluation Results")
    )
    admin.add_view(DimensionScoreAdminView(DimensionScore, label="Dimension Scores"))
    admin.add_view(RedFlagAdminView(RedFlag, label="Red Flags"))

    admin.mount_to(app)
