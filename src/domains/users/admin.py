from starlette.requests import Request
from starlette_admin.actions import action
from starlette_admin.contrib.sqla import ModelView
from starlette_admin.exceptions import ActionFailed

from src.core.security import UNUSABLE_PASSWORD, hash_password
from src.domains.users.models import User


class UserAdminView(ModelView):
    """Admin view for the User model."""

    column_list = ["id", "email", "role", "tenant_id", "is_active", "created_at"]
    column_searchable_list = ["email"]
    column_detail_list = [
        "id",
        "email",
        "role",
        "tenant_id",
        "is_active",
        "created_at",
        "updated_at",
    ]

    exclude_fields_from_create = ["hashed_password"]
    exclude_fields_from_edit = ["hashed_password"]

    # Register our custom row-level action
    actions = ["set_password"]

    async def after_create(self, request: Request, obj: User) -> None:
        """Lock the account until a password is explicitly set."""
        obj.hashed_password = UNUSABLE_PASSWORD
        # The session is still open — flush so the change persists.
        await request.state.session.commit()

    @action(
        name="set_password",
        text="Set Password",
        confirmation="Enter a new password for the selected user.",
        submit_btn_text="Update",
        submit_btn_class="btn-warning",
        form="""
        <form>
          <div class="mt-3">
            <label class="form-label">New password</label>
            <input type="password" class="form-control" name="new_password" required minlength="8">
          </div>
          <div class="mt-3">
            <label class="form-label">Confirm password</label>
            <input type="password" class="form-control" name="confirm_password" required minlength="8">
          </div>
        </form>
        """,
    )
    async def set_password(self, request: Request, pk: list[str]) -> str:
        form = await request.form()
        new_password = form.get("new_password", "")
        confirm = form.get("confirm_password", "")

        if not isinstance(new_password, str) or not isinstance(confirm, str):
            raise ActionFailed("Invalid form submission.")

        if not new_password:
            raise ActionFailed("Password cannot be empty.")
        if new_password != confirm:
            raise ActionFailed("Passwords do not match.")
        if len(new_password) < 8:
            raise ActionFailed("Password must be at least 8 characters.")

        session = request.state.session

        updated = 0
        for user_pk in pk:
            result = await session.get(User, user_pk)
            if result is not None:
                result.hashed_password = hash_password(new_password)
                updated += 1

        await session.commit()
        return f"Password updated for {updated} user(s)."
