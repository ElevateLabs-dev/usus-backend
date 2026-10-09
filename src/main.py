from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from src.admin import setup_admin
from src.core.config import settings
from src.domains.auth.router import router as auth_router
from src.domains.evaluations.router import router as evaluations_router
from src.domains.progress.router import router as progress_router
from src.domains.scenarios.router import router as scenarios_router
from src.domains.simulations.router import router as simulations_router
from src.domains.users.router import router as users_router

API_DESCRIPTION = """
Backend for **Usus** — an AI simulation platform where staff practise realistic
customer conversations and get scored feedback.

### Signing in
1. `POST /api/v1/auth/token` with your email and password (click **Authorize**).
2. Send the returned token as `Authorization: Bearer <token>`.

### Trainee onboarding
Trainees do not sign up themselves. A company admin or manager adds them
(`/api/v1/users/trainees`, `/bulk`, or an Excel `/import`). Each trainee is
emailed a temporary password and must call `POST /api/v1/auth/change-password`
on first sign-in — until then other endpoints return **403 Password change
required**.
"""

OPENAPI_TAGS = [
    {"name": "Auth", "description": "Sign in and change password."},
    {
        "name": "Users & Trainees",
        "description": "Your profile, and how organizations add and manage trainees.",
    },
    {"name": "Scenarios", "description": "Training scenarios for your organization."},
    {
        "name": "Simulations",
        "description": "Role-play sessions with the AI customer, and their evaluation.",
    },
    {
        "name": "Progress",
        "description": "Trainee progress, and a team overview for managers.",
    },
    {"name": "Evaluations", "description": "Evaluation jobs."},
]


def create_app() -> FastAPI:
    """Factory function to create the Usus Backend"""

    app = FastAPI(
        title="Usus Backend API",
        description=API_DESCRIPTION,
        version="0.1.0",
        openapi_tags=OPENAPI_TAGS,
    )

    # SessionMiddleware is required by Starlette-Admin for cookie-based auth sessions.
    # It must be added before the admin is mounted.
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

    # Register domain routers
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(simulations_router)
    app.include_router(evaluations_router)
    app.include_router(scenarios_router)
    app.include_router(progress_router)

    # Mount the admin panel at /admin
    setup_admin(app)

    @app.get("/health")
    async def root_health_check():
        return {"status": "ok", "service": "usus-backend"}

    return app


app = create_app()

if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from src.cli.runner import run_cli

        try:
            asyncio.run(run_cli())
        except KeyboardInterrupt:
            print("\nExiting CLI...")
    else:
        import uvicorn

        uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
