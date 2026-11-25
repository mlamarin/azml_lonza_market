"""Request and response schemas of the prediction API.

They are the API side of the contract with the Streamlit app. FastAPI publishes
them in its OpenAPI document (/openapi.json), which is what the app reads.
"""

from pydantic import BaseModel, ConfigDict, Field

from azml_market.curation.schema import IndicationArea, Modality, Phase, SponsorType


class TransitionFeatures(BaseModel):
    """The model inputs for one phase transition."""

    model_config = ConfigDict(extra="forbid")

    from_phase: Phase
    modality: Modality
    indication_area: IndicationArea
    sponsor_type: SponsorType
    biomarker_selected: bool
    orphan_designation: bool


class PredictRequest(BaseModel):
    transitions: list[TransitionFeatures] = Field(min_length=1, max_length=1000)


class Prediction(BaseModel):
    p_progress: float = Field(ge=0, le=1, description="Predicted probability of moving to the next phase")


class PredictResponse(BaseModel):
    model_version: str
    model_kind: str
    model_ref: str = Field(description="What the caller asked for: an alias such as champion, or a version number")
    predictions: list[Prediction]


class ModelInfo(BaseModel):
    version: str
    model_kind: str
    aliases: list[str]
    validation_status: str | None
    validation_reason: str | None
    test_brier: float | None
    test_spiegelhalter_p: float | None


class CalibrationBin(BaseModel):
    bin_lower: float
    bin_upper: float
    mean_predicted: float
    observed_rate: float
    n: int


class CalibrationResponse(BaseModel):
    model_version: str
    model_kind: str
    test_brier: float
    test_spiegelhalter_p: float
    truth_oracle_brier: float
    model_curve: list[CalibrationBin]
    truth_curve: list[CalibrationBin] = Field(description="Same bins computed with the synthetic truth p_true")
