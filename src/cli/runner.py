import uuid
import asyncio

from src.core.database import AsyncSessionLocal
from src.infrastructure.llm.factory import get_llm_provider

from src.domains.scenarios.models import Scenario
from src.domains.scenarios.crud import CRUDScenario
from src.domains.scenarios.service import ScenarioService

from src.domains.simulations.models import Session, Message
from src.domains.simulations.crud import CRUDSession, CRUDMessage
from src.domains.simulations.service import SimulationService

from src.domains.evaluations.models import EvaluationResult, DimensionScore, RedFlag
from src.domains.evaluations.crud import (
    CRUDEvaluationResult,
    CRUDDimensionScore,
    CRUDRedFlag,
)
from src.domains.evaluations.service import EvaluationService


async def run_cli():
    print("Welcome to the Usus Simulation Engine CLI!")
    print("Initializing services...")

    # We use a fixed tenant_id for the CLI testing purposes
    tenant_id = uuid.uuid5(uuid.NAMESPACE_DNS, "usus-cli-tenant")

    # Initialize Services
    scenario_repo = CRUDScenario(Scenario)
    scenario_service = ScenarioService(scenario_repo)

    session_repo = CRUDSession(Session)
    message_repo = CRUDMessage(Message)

    eval_result_repo = CRUDEvaluationResult(EvaluationResult)
    dimension_score_repo = CRUDDimensionScore(DimensionScore)
    red_flag_repo = CRUDRedFlag(RedFlag)

    llm_provider = get_llm_provider()
    evaluation_service = EvaluationService(
        eval_result_repo, dimension_score_repo, red_flag_repo, llm_provider
    )

    simulation_service = SimulationService(
        session_repo, message_repo, scenario_repo, llm_provider, evaluation_service
    )

    async with AsyncSessionLocal() as db:
        print("Seeding default scenarios if needed...")
        scenarios = await scenario_service.seed_defaults(db, tenant_id)

        print("\n--- Available Scenarios ---")
        for idx, s in enumerate(scenarios):
            print(
                f"{idx + 1}. {s.name} ({s.difficulty.value.upper()}) - Persona: {s.persona.value}"
            )
            print(f"   {s.description}")

        choice = await asyncio.to_thread(
            input, "\nSelect a scenario by number (or type 'q' to quit): "
        )
        if choice.lower() == "q":
            return

        try:
            choice_idx = int(choice) - 1
            selected_scenario = scenarios[choice_idx]
        except (ValueError, IndexError):
            print("Invalid selection. Exiting.")
            return

        print(f"\nStarting session for: {selected_scenario.name}")
        session = await simulation_service.start_session(
            db, tenant_id, selected_scenario.id
        )

        print(
            f"\n[System]: You are connected to a {selected_scenario.persona.value} customer. Type '/end' to finish the simulation.\n"
        )

        # Initial prompt from the customer? No, usually the trainee says "Hello" first.
        # But let's prompt the trainee to speak.
        while True:
            trainee_input = await asyncio.to_thread(input, "You: ")
            if trainee_input.strip().lower() in ["/end", "/quit"]:
                break

            if not trainee_input.strip():
                continue

            print("Customer is typing...")
            try:
                model_msg = await simulation_service.send_message(
                    db, tenant_id, session.id, trainee_input
                )
                print(f"Customer: {model_msg.content}")
            except Exception as e:
                print(f"An error occurred communicating with the LLM: {e}")
                break

        print("\nEnding session and generating evaluation. Please wait...")
        try:
            _, eval_result = await simulation_service.end_session(
                db, tenant_id, session.id
            )

            print("\n==================================")
            print("        EVALUATION RESULT         ")
            print("==================================")
            print(f"Overall Score: {eval_result.overall_score}/100")
            print(f"\nSummary:\n{eval_result.summary}")

            # Since dimension scores and red flags are lazily loaded or need to be refetched by relationships,
            # we will just query them directly if our eval_result doesn't have them preloaded dynamically here
            # For simplicity in Phase A5, they might not be attached to eval_result if not eagerly loaded.
            # But let's assume they were evaluated successfully.
            print("\nSimulation ended successfully.")

        except Exception as e:
            print(f"An error occurred during evaluation: {e}")


if __name__ == "__main__":
    asyncio.run(run_cli())
