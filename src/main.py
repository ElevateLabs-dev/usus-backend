from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from src.admin import setup_admin
from src.core.config import settings
from src.domains.evaluations.router import router as evaluations_router
from src.domains.simulations.router import router as simulations_router


def create_app() -> FastAPI:
    """Factory function to create the Usus Backend"""

    app = FastAPI(
        title="Usus Backend API",
        description="Enterprise-grade backend for Usus - an AI simulation platform",
        version="0.1.0",
    )

    # SessionMiddleware is required by Starlette-Admin for cookie-based auth sessions.
    # It must be added before the admin is mounted.
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

    # Register domain routers
    app.include_router(simulations_router)
    app.include_router(evaluations_router)

    # Mount the admin panel at /admin
    setup_admin(app)

    @app.get("/health")
    async def root_health_check():
        return {"status": "ok", "service": "usus-backend"}

    return app


app = create_app()

if __name__ == "__main__":
    import sys
    import asyncio

    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from src.cli.runner import run_cli

        try:
            asyncio.run(run_cli())
        except KeyboardInterrupt:
            print("\nExiting CLI...")
    else:
        import uvicorn
        uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
