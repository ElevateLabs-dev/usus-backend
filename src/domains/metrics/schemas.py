from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MetricRead(BaseModel):
    id: UUID | None = Field(description="Null for the default metrics")
    key: str = Field(description="Use this in a scenario's `metrics`")
    name: str
    description: str
    is_default: bool


class MetricCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(
        min_length=10,
        max_length=2000,
        description="What good looks like; the evaluator scores against it",
    )

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Upselling",
                "description": "Offers a relevant upgrade or add-on once the "
                "customer's problem is solved, without being pushy.",
            }
        }
    }


class MetricUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, min_length=10, max_length=2000)

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None
