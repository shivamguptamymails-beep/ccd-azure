"""Request/response models for the inference API.

The AI4I 2020 dataset's raw column names ("Air temperature [K]", etc.) are not
valid Python identifiers, so each field is exposed to API callers under a
clean snake_case name (e.g. `air_temperature`) via a pydantic alias, and
`to_raw_row()` converts a validated reading back to the exact column names
the saved model pipelines expect.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RAW_COLUMNS = [
    "Type", "Air temperature [K]", "Process temperature [K]",
    "Rotational speed [rpm]", "Torque [Nm]", "Tool wear [min]",
]


class MachineReading(BaseModel):
    """One machine's raw sensor reading, in the same units as the training data."""

    model_config = ConfigDict(populate_by_name=True)

    machine_id: Optional[str] = Field(
        default=None, description="Caller-supplied identifier, echoed back in the response")
    type: Literal["L", "M", "H"] = Field(
        alias="Type", description="Product quality variant")
    air_temperature: float = Field(alias="Air temperature [K]", ge=290, le=320)
    process_temperature: float = Field(alias="Process temperature [K]", ge=295, le=320)
    rotational_speed: float = Field(alias="Rotational speed [rpm]", gt=0, le=5000)
    torque: float = Field(alias="Torque [Nm]", ge=0, le=200)
    tool_wear: float = Field(alias="Tool wear [min]", ge=0, le=260)

    def to_raw_row(self) -> dict:
        return {
            "Type": self.type,
            "Air temperature [K]": self.air_temperature,
            "Process temperature [K]": self.process_temperature,
            "Rotational speed [rpm]": self.rotational_speed,
            "Torque [Nm]": self.torque,
            "Tool wear [min]": self.tool_wear,
        }


class BatchPredictionRequest(BaseModel):
    readings: list[MachineReading]


class FeatureContribution(BaseModel):
    feature: str
    value: float
    contribution: float
    effect: Literal["Raises risk", "Lowers risk"]


class PredictionResult(BaseModel):
    machine_id: str
    priority_rank: int
    failure_probability: float
    risk_level: Literal["Healthy", "At Risk", "Critical"]
    recommendation: str
    likely_cause: str
    failure_mode_probabilities: dict[str, float]


class BatchPredictionResponse(BaseModel):
    results: list[PredictionResult]


class ExplanationResponse(BaseModel):
    machine_id: str
    contributions: list[FeatureContribution]


class ModelMetadata(BaseModel):
    final_model: str
    thresholds: dict[str, float]
    raw_input_columns: list[str]
    model_comparison: list[dict]
    model_version: str = "dev"
    model_source: Literal["blob", "image"] = "image"


class HistoryResponse(BaseModel):
    enabled: bool = Field(description="False when no Cosmos DB connection is configured")
    records: list[dict]
