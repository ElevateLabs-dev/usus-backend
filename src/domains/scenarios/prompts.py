from src.domains.scenarios.models import Scenario


def build_customer_prompt(scenario: Scenario) -> str:
    """
    The AI customer's instructions for a scenario.

    Uses the hand-written system_prompt when present; otherwise builds one from
    the brief fields, so content writers only need to fill in the brief.
    """
    if scenario.system_prompt and scenario.system_prompt.strip():
        return scenario.system_prompt

    name = scenario.customer_name or "the customer"
    lines = [
        f"You are role-playing a customer named {name} contacting customer support. "
        f"Scenario: {scenario.name}. {scenario.description}",
    ]
    details = [
        ("Your personality", scenario.customer_personality),
        ("How you feel right now", scenario.customer_emotion or scenario.persona.value),
        ("Your background", scenario.customer_background),
        ("What happened", scenario.situation),
        ("What you want", scenario.customer_goal),
        ("If the agent handles you badly", scenario.escalation_behavior),
        ("What would satisfy you", scenario.success_criteria),
    ]
    lines += [f"{label}: {value}" for label, value in details if value]
    lines.append(
        "Rules:\n"
        "- Stay in character as the customer for the whole conversation; never "
        "mention that you are an AI or that this is training.\n"
        "- Open the conversation by explaining your problem in your own words.\n"
        "- React realistically to how the agent treats you: calm down when they "
        "listen and help, become more upset when they are dismissive or vague.\n"
        "- Do not solve the problem for the agent or offer solutions yourself.\n"
        "- Keep each reply short (2-5 sentences)."
    )
    return "\n\n".join(lines)
