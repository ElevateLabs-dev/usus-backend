from starlette_admin.contrib.sqla import ModelView
from starlette_admin.fields import EnumField, JSONField, StringField, TextAreaField

from src.core.training import TrainingCategory
from src.domains.scenarios.models import CustomerPersona, DifficultyLevel


class ScenarioAdminView(ModelView):
	"""Admin view for the Scenario model."""

	fields = [
		"id",
		"tenant_id",
		"name",
		"description",
		EnumField("category", enum=TrainingCategory, required=False),
		EnumField("persona", enum=CustomerPersona, required=True),
		EnumField("difficulty", enum=DifficultyLevel, required=True),
		JSONField(
			"skills",
			label="Skills: accuracy, empathy, clarity, policy, resolution, "
			"de_escalation, efficiency",
		),
		"estimated_minutes",
		StringField("customer_name"),
		StringField("customer_personality"),
		StringField("customer_emotion"),
		TextAreaField("customer_background"),
		TextAreaField("situation", label="Situation (what happened)"),
		TextAreaField("customer_goal", label="What the customer wants"),
		TextAreaField("trainee_objective"),
		JSONField(
			"important_information",
			label='Important information: [{"label": ..., "content": ...}]',
		),
		TextAreaField(
			"escalation_behavior", label="Escalation behaviour (hidden from trainees)"
		),
		TextAreaField(
			"success_criteria", label="Success criteria (hidden from trainees)"
		),
		TextAreaField(
			"system_prompt",
			label="AI customer prompt (optional; built from the brief if empty)",
		),
		"created_at",
		"updated_at",
	]

	column_list = [
		"id",
		"tenant_id",
		"name",
		"category",
		"persona",
		"difficulty",
		"created_at",
	]
	column_searchable_list = ["name", "description"]
