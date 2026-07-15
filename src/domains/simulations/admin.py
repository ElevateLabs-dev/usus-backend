from starlette_admin.contrib.sqla import ModelView
from starlette_admin.fields import EnumField

from src.domains.simulations.models import Message, MessageRole, Session, SessionStatus


class SessionAdminView(ModelView):
    """Admin view for the Session model."""

    fields = [
        "id",
        "tenant_id",
        "scenario_id",
        EnumField("status", enum=SessionStatus, required=True),
        "created_at",
        "updated_at",
    ]

    column_list = ["id", "tenant_id", "scenario_id", "status", "created_at"]
    column_detail_list = [
        "id",
        "tenant_id",
        "scenario_id",
        "status",
        "created_at",
        "updated_at",
    ]


class MessageAdminView(ModelView):
    """Admin view for the Message model."""

    fields = [
        "id",
        "tenant_id",
        "session_id",
        EnumField("role", enum=MessageRole, required=True),
        "content",
        "created_at",
        "updated_at",
    ]

    column_list = [
        "id",
        "tenant_id",
        "session_id",
        "role",
        "content",
        "created_at",
    ]
    column_detail_list = [
        "id",
        "tenant_id",
        "session_id",
        "role",
        "content",
        "created_at",
        "updated_at",
    ]
    column_searchable_list = ["content"]
