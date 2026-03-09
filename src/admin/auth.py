from starlette.requests import Request
from starlette.responses import Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import FormValidationError

from src.core.config import settings


class AdminAuthProvider(AuthProvider):
    """
    Simple credentials-based auth provider for the Starlette-Admin panel.

    Credentials are read from settings (ADMIN_USERNAME / ADMIN_PASSWORD)
    so they never live in source control.
    """

    async def login(
        self,
        username: str,
        password: str,
        remember_me: bool,
        request: Request,
        response: Response,
    ) -> Response:
        if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
            # Store the username in the session so is_authenticated can read it.
            request.session.update({"admin_username": username})
            return response

        raise FormValidationError(
            {"password": "Invalid username or password. Please try again."}
        )

    async def is_authenticated(self, request: Request) -> bool:
        return bool(request.session.get("admin_username"))

    def get_admin_user(self, request: Request) -> AdminUser:
        return AdminUser(username=request.session.get("admin_username", "admin"))

    async def logout(self, request: Request, response: Response) -> Response:
        request.session.clear()
        return response
