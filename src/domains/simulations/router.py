from fastapi import APIRouter

# initialize router
router = APIRouter(
    prefix="/api/v1/simulations",
    tags=["Simulations"],
)


# native async support is essential for WebRTC and AI workflows
@router.get("/health")
async def simulation_health_check():
    return {"status": "ok", "domain": "simulations"}
