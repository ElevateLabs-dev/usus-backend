"""
Training catalog shared by scenarios and evaluations (from the MVP plan).

- TrainingCategory: what a scenario trains (scenarios are grouped by it).
- SkillDimension: the 7 dimensions every session is scored on. A scenario's
  "skills tested" are a subset of these.
"""

import enum


class TrainingCategory(str, enum.Enum):
    DE_ESCALATION = "de_escalation"
    COMMUNICATION = "communication"
    PROBLEM_RESOLUTION = "problem_resolution"
    EMPATHY = "empathy"
    POLICY_COMPLIANCE = "policy_compliance"


# (display name, description shown to trainees)
CATEGORY_INFO: dict[TrainingCategory, tuple[str, str]] = {
    TrainingCategory.DE_ESCALATION: (
        "De-escalation",
        "Learn how to calm difficult or angry customers.",
    ),
    TrainingCategory.COMMUNICATION: (
        "Communication",
        "Practice clear and effective customer communication.",
    ),
    TrainingCategory.PROBLEM_RESOLUTION: (
        "Problem Resolution",
        "Practice identifying problems and finding appropriate solutions.",
    ),
    TrainingCategory.EMPATHY: (
        "Empathy",
        "Practice responding appropriately to customer emotions.",
    ),
    TrainingCategory.POLICY_COMPLIANCE: (
        "Policy & Compliance",
        "Practice applying company policies while maintaining good customer "
        "relationships.",
    ),
}


class SkillDimension(str, enum.Enum):
    ACCURACY = "accuracy"
    EMPATHY = "empathy"
    CLARITY = "clarity"
    POLICY = "policy"
    RESOLUTION = "resolution"
    DE_ESCALATION = "de_escalation"
    EFFICIENCY = "efficiency"


# (display name, what the evaluator scores)
DIMENSION_INFO: dict[SkillDimension, tuple[str, str]] = {
    SkillDimension.ACCURACY: (
        "Accuracy",
        "Gives correct, truthful information; no invented facts or promises the "
        "company cannot keep.",
    ),
    SkillDimension.EMPATHY: (
        "Empathy",
        "Recognises and acknowledges the customer's feelings and the impact on them.",
    ),
    SkillDimension.CLARITY: (
        "Clarity",
        "Explains clearly and simply; the customer always knows what happens next.",
    ),
    SkillDimension.POLICY: (
        "Policy",
        "Follows company policy and protects customer data, while still helping.",
    ),
    SkillDimension.RESOLUTION: (
        "Resolution",
        "Identifies the real problem and reaches an appropriate, concrete solution.",
    ),
    SkillDimension.DE_ESCALATION: (
        "De-escalation",
        "Lowers the customer's frustration instead of increasing it.",
    ),
    SkillDimension.EFFICIENCY: (
        "Efficiency",
        "Resolves the issue without unnecessary back-and-forth or delays.",
    ),
}


def category_name(category: TrainingCategory | str | None) -> str | None:
    if category is None:
        return None
    return CATEGORY_INFO[TrainingCategory(category)][0]


def dimension_name(dimension: SkillDimension | str) -> str:
    return DIMENSION_INFO[SkillDimension(dimension)][0]
