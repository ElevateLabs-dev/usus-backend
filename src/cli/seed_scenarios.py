import asyncio
import uuid

from src.core.database import AsyncSessionLocal
from src.domains.scenarios.crud import CRUDScenario
from src.domains.scenarios.models import Scenario
from src.domains.scenarios.service import ScenarioService


async def _seed_scenarios() -> None:
    print("=== Seed Default Scenarios ===")
    tenant_raw = (
        await asyncio.to_thread(
            input,
            "Tenant ID (leave blank for local CLI tenant): ",
        )
    ).strip()

    if tenant_raw:
        try:
            tenant_id = uuid.UUID(tenant_raw)
        except ValueError:
            print("Invalid UUID for tenant_id.")
            return
    else:
        tenant_id = uuid.uuid5(uuid.NAMESPACE_DNS, "usus-cli-tenant")

    scenario_repo = CRUDScenario(Scenario)
    scenario_service = ScenarioService(scenario_repo)

    async with AsyncSessionLocal() as db:
        existing = await scenario_service.list_all_scenarios(db, tenant_id)
        scenarios = await scenario_service.seed_defaults(db, tenant_id)

        if existing:
            print(f"Found {len(existing)} existing scenario(s) for tenant {tenant_id}.")
        else:
            print(f"Created {len(scenarios)} default scenario(s) for tenant {tenant_id}.")

        print("\n--- Scenarios ---")
        for idx, scenario in enumerate(scenarios, start=1):
            print(
                f"{idx}. {scenario.name} ({scenario.difficulty.value.upper()}) - Persona: {scenario.persona.value}"
            )
            print(f"   {scenario.description}")


def seed_scenarios() -> None:
    """Entry-point for the seed-scenarios CLI command."""
    asyncio.run(_seed_scenarios())
