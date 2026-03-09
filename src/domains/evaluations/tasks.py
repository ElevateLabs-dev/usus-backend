from src.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3)
def generate_evaluation_report(self, simulation_id: str, tenant_id: str):
    """Expensive: calls LLM to generate a scored evaluation report."""
    # 1. Fetch simulation data from DB
    # 2. Call OpenAI/Anthropic to generate evaluation
    # 3. Save results back to DB
    return {"simulation_id": simulation_id, "status": "completed"}
