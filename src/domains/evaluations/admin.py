from starlette_admin.contrib.sqla import ModelView

from src.domains.evaluations.models import DimensionScore, EvaluationResult, RedFlag


class EvaluationResultAdminView(ModelView):
    """Admin view for the EvaluationResult model."""

    fields = [
        "id",
        "tenant_id",
        "session_id",
        "overall_score",
        "summary",
        "created_at",
        "updated_at",
    ]

    column_list = [
        "id",
        "tenant_id",
        "session_id",
        "overall_score",
        "created_at",
    ]
    column_detail_list = [
        "id",
        "tenant_id",
        "session_id",
        "overall_score",
        "summary",
        "created_at",
        "updated_at",
    ]
    column_searchable_list = ["summary"]


class DimensionScoreAdminView(ModelView):
    """Admin view for the DimensionScore model."""

    fields = [
        "id",
        "evaluation_id",
        "dimension_name",
        "score",
        "rationale",
        "created_at",
        "updated_at",
    ]

    column_list = ["id", "evaluation_id", "dimension_name", "score", "created_at"]
    column_detail_list = [
        "id",
        "evaluation_id",
        "dimension_name",
        "score",
        "rationale",
        "created_at",
        "updated_at",
    ]
    column_searchable_list = ["dimension_name", "rationale"]


class RedFlagAdminView(ModelView):
    """Admin view for the RedFlag model."""

    fields = [
        "id",
        "evaluation_id",
        "reason",
        "description",
        "created_at",
        "updated_at",
    ]

    column_list = ["id", "evaluation_id", "reason", "created_at"]
    column_detail_list = [
        "id",
        "evaluation_id",
        "reason",
        "description",
        "created_at",
        "updated_at",
    ]
    column_searchable_list = ["reason", "description"]
