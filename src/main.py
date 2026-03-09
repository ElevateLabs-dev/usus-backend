from fastapi import FastAPI
from src.domains.evaluations.router import router as evaluations_router
from src.domains.simulations.router import router as simulations_router


def create_app() -> FastAPI:
    """Factory function to create the Usus Backend"""

    app = FastAPI(
        title="Usus Backend API",
        description="Enterprise-grade backend for Usus - an AI simulation platform",
        version="0.1.0",
    )

    # Register domain routers
    app.include_router(simulations_router)
    app.include_router(evaluations_router)

    @app.get("/health")
    async def root_health_check():
        return {"status": "ok", "service": "usus-backend"}

    return app


app = create_app()
