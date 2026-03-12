from starlette.requests import Request
from starlette.responses import Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import FormValidationError

from src.core.database import AsyncSessionLocal
from src.core.dependencies import UserRole
from src.core.security import verify_password
from src.domains.users.crud import user as user_repo


class AdminAuthProvider(AuthProvider):
    """
    Authenticates admin-panel logins against the User table.
    Only PLATFORM_ADMIN users are granted access.
    """

    async def login(
        self,
        username: str,
        password: str,
        remember_me: bool,
        request: Request,
        response: Response,
    ) -> Response:
        invalid = FormValidationError(
            {"password": "Invalid username or password. Please try again."}
        )

        async with AsyncSessionLocal() as db:
            user = await user_repo.get_by_email(db, username)

        if user is None or not user.is_active:
            raise invalid
        if user.role != UserRole.PLATFORM_ADMIN.value:
            raise invalid
        if not verify_password(password, user.hashed_password):
            raise invalid

        request.session.update({"admin_username": user.email})
        return response

    async def is_authenticated(self, request: Request) -> bool:
        return bool(request.session.get("admin_username"))

    def get_admin_user(self, request: Request) -> AdminUser:
        return AdminUser(username=request.session.get("admin_username", "admin"))

    async def logout(self, request: Request, response: Response) -> Response:
        request.session.clear()
        return response
