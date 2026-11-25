"""Schema contract for raw clinical-progression records.

This is the contract between ingestion (the data producer) and curation.
It is defined here, independently of the generator, so that a test can check
that what the generator writes still satisfies what curation expects.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1

NEXT_PHASE = {"I": "II", "II": "III", "III": "Filing"}

# Allowed values, shared with the prediction API.
IndicationArea = Literal[
    "oncology",
    "immunology",
    "neurology",
    "infectious_disease",
    "rare_disease",
    "cardiometabolic",
]
Modality = Literal[
    "small_molecule",
    "monoclonal_antibody",
    "antibody_drug_conjugate",
    "cell_therapy",
    "gene_therapy",
    "peptide",
]
Phase = Literal["I", "II", "III"]
SponsorType = Literal["large_pharma", "biotech"]


class TransitionRecord(BaseModel):
    """One phase transition of one candidate-indication pair."""

    # Unknown columns are an error: a silent extra field usually means a producer-side change.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    record_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    indication_area: IndicationArea
    modality: Modality
    from_phase: Phase
    to_phase: Literal["II", "III", "Filing"]
    sponsor_type: SponsorType
    biomarker_selected: bool
    orphan_designation: bool
    start_year: int = Field(ge=1990, le=2100)
    batch_id: str = Field(min_length=1)
    data_origin: Literal["synthetic"]
    progressed: int = Field(ge=0, le=1)

    @model_validator(mode="after")
    def to_phase_follows_from_phase(self) -> "TransitionRecord":
        if NEXT_PHASE[self.from_phase] != self.to_phase:
            raise ValueError(
                f"to_phase {self.to_phase!r} does not follow from_phase {self.from_phase!r}"
            )
        return self
