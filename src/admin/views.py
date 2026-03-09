from starlette.requests import Request
from starlette_admin.contrib.sqla import ModelView

from src.domains.tenants.models import Tenant


class TenantAdminView(ModelView):
    """
    Admin view for the Tenant model.
    """

    # Column visibility in the list view
    column_list = ["id", "name", "is_active", "created_at", "updated_at"]

    # These columns will appear in the detail/search view
    column_detail_list = ["id", "name", "is_active", "created_at", "updated_at"]
