from starlette_admin.contrib.sqla import ModelView
from starlette_admin.fields import EnumField

from src.domains.scenarios.models import DifficultyLevel, Scenario, CustomerPersona


class ScenarioAdminView(ModelView):
	"""Admin view for the Scenario model."""

	fields = [
		"id",
		"tenant_id",
		"name",
		"description",
		"system_prompt",
		EnumField("persona", enum=CustomerPersona, required=True),
		EnumField("difficulty", enum=DifficultyLevel, required=True),
		"created_at",
		"updated_at",
	]

	column_list = [
		"id",
		"tenant_id",
		"name",
		"persona",
		"difficulty",
		"created_at",
	]
	column_detail_list = [
		"id",
		"tenant_id",
		"name",
		"description",
		"system_prompt",
		"persona",
		"difficulty",
		"created_at",
		"updated_at",
	]
	column_searchable_list = ["name", "description"]

