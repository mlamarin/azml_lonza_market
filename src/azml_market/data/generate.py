"""Generate a SYNTHETIC clinical-progression dataset, in batches.

One row is one phase transition of one candidate-indication pair
(for example SYN-C0012 / oncology / Phase II -> Phase III).

The outcome is drawn from a known logistic model, so the true probability of
each row is known. It is written to a separate truth file, never given to the
model, and used later as ground truth for calibration.

All coefficients and proportions below are ARBITRARY ILLUSTRATIVE VALUES.
They are not published success rates and say nothing about real clinical
progression.

Run with: uv run generate-data --seed 42
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

PHASES = ["I", "II", "III"]
NEXT_PHASE = {"I": "II", "II": "III", "III": "Filing"}

MODALITIES = [
    "small_molecule",
    "monoclonal_antibody",
    "antibody_drug_conjugate",
    "cell_therapy",
    "gene_therapy",
    "peptide",
]
INDICATION_AREAS = [
    "oncology",
    "immunology",
    "neurology",
    "infectious_disease",
    "rare_disease",
    "cardiometabolic",
]
AREA_CODES = {
    "oncology": "ONC",
    "immunology": "IMM",
    "neurology": "NEU",
    "infectious_disease": "INF",
    "rare_disease": "RAR",
    "cardiometabolic": "CMT",
}

# Truth model: logit(p_true) = sum of the terms below. Arbitrary values.
COEF_PHASE = {"I": 0.4, "II": -0.6, "III": 0.5}
COEF_MODALITY = {
    "small_molecule": 0.0,
    "monoclonal_antibody": 0.3,
    "antibody_drug_conjugate": 0.1,
    "cell_therapy": -0.3,
    "gene_therapy": -0.2,
    "peptide": 0.0,
}
COEF_AREA = {
    "oncology": -0.4,
    "immunology": 0.1,
    "neurology": -0.3,
    "infectious_disease": 0.3,
    "rare_disease": 0.2,
    "cardiometabolic": 0.0,
}
COEF_BIOMARKER = 0.5
COEF_ORPHAN = 0.3
COEF_LARGE_PHARMA = 0.2
# One interaction, so that a purely additive model is slightly misspecified.
COEF_BIOMARKER_X_ONCOLOGY = 0.4

# Sampling proportions. The shifted batch changes the covariate mix only;
# the truth model stays the same.
MODALITY_PROBS = [0.35, 0.25, 0.10, 0.08, 0.07, 0.15]
MODALITY_PROBS_SHIFTED = [0.25, 0.20, 0.10, 0.18, 0.15, 0.12]
BIOMARKER_PROB = 0.3
BIOMARKER_PROB_SHIFTED = 0.5
LARGE_PHARMA_PROB = 0.4

N_BATCHES = 4
SHIFTED_BATCH = "batch_04"

RAW_COLUMNS = [
    "record_id",
    "candidate_id",
    "indication_area",
    "modality",
    "from_phase",
    "to_phase",
    "sponsor_type",
    "biomarker_selected",
    "orphan_designation",
    "start_year",
    "batch_id",
    "data_origin",
    "progressed",
]


def true_probability(
    from_phase: str,
    modality: str,
    indication_area: str,
    biomarker_selected: bool,
    orphan_designation: bool,
    sponsor_type: str,
) -> float:
    """Probability of progressing to the next phase under the truth model."""
    logit = (
        COEF_PHASE[from_phase]
        + COEF_MODALITY[modality]
        + COEF_AREA[indication_area]
        + COEF_BIOMARKER * biomarker_selected
        + COEF_ORPHAN * orphan_designation
        + COEF_LARGE_PHARMA * (sponsor_type == "large_pharma")
        + COEF_BIOMARKER_X_ONCOLOGY * (biomarker_selected and indication_area == "oncology")
    )
    return float(1.0 / (1.0 + np.exp(-logit)))


def generate_batch(
    rng: np.random.Generator, batch_id: str, n_candidates: int, first_candidate: int, base_year: int
) -> list[dict]:
    """Simulate the transition history of n_candidates candidates. Returns rows with p_true."""
    shifted = batch_id == SHIFTED_BATCH
    modality_probs = MODALITY_PROBS_SHIFTED if shifted else MODALITY_PROBS
    biomarker_prob = BIOMARKER_PROB_SHIFTED if shifted else BIOMARKER_PROB

    rows = []
    for i in range(n_candidates):
        candidate_id = f"SYN-C{first_candidate + i:04d}"
        modality = rng.choice(MODALITIES, p=modality_probs)
        sponsor_type = "large_pharma" if rng.random() < LARGE_PHARMA_PROB else "biotech"
        n_areas = rng.integers(1, 4)
        areas = rng.choice(INDICATION_AREAS, size=n_areas, replace=False)

        for area in areas:
            biomarker_selected = bool(rng.random() < biomarker_prob)
            orphan_designation = bool(rng.random() < (0.6 if area == "rare_disease" else 0.1))
            year = base_year + int(rng.integers(0, 3))

            # Attempt transitions in sequence, stop at the first failure.
            for phase in PHASES:
                p_true = true_probability(
                    phase, modality, area, biomarker_selected, orphan_designation, sponsor_type
                )
                progressed = int(rng.random() < p_true)
                rows.append(
                    {
                        "record_id": f"{candidate_id}-{AREA_CODES[area]}-P{phase}",
                        "candidate_id": candidate_id,
                        "indication_area": str(area),
                        "modality": str(modality),
                        "from_phase": phase,
                        "to_phase": NEXT_PHASE[phase],
                        "sponsor_type": sponsor_type,
                        "biomarker_selected": biomarker_selected,
                        "orphan_designation": orphan_designation,
                        "start_year": year,
                        "batch_id": batch_id,
                        "data_origin": "synthetic",
                        "progressed": progressed,
                        "p_true": p_true,
                    }
                )
                if not progressed:
                    break
                year += int(rng.integers(1, 4))
    return rows


def generate(seed: int, n_candidates: int = 150) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate all batches. Returns (raw, truth) data frames sharing record_id."""
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(1, N_BATCHES + 1):
        rows += generate_batch(
            rng,
            batch_id=f"batch_{k:02d}",
            n_candidates=n_candidates,
            first_candidate=(k - 1) * n_candidates + 1,
            base_year=2008 + 2 * k,
        )
    df = pd.DataFrame(rows)
    return df[RAW_COLUMNS], df[["record_id", "batch_id", "p_true"]]


def write_outputs(raw: pd.DataFrame, truth: pd.DataFrame, out_dir: Path, seed: int) -> None:
    """Write one CSV and one JSON raw file, and one truth CSV, per batch."""
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    (out_dir / "truth").mkdir(parents=True, exist_ok=True)
    for batch_id, batch in raw.groupby("batch_id"):
        batch.to_csv(out_dir / "raw" / f"{batch_id}.csv", index=False)
        document = {
            "synthetic": True,
            "batch_id": batch_id,
            "seed": seed,
            "records": json.loads(batch.to_json(orient="records")),
        }
        (out_dir / "raw" / f"{batch_id}.json").write_text(json.dumps(document, indent=2))
        batch_truth = truth[truth["batch_id"] == batch_id][["record_id", "p_true"]]
        batch_truth.to_csv(out_dir / "truth" / f"{batch_id}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="generate-data", description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-candidates", type=int, default=150, help="candidates per batch")
    parser.add_argument("--out", type=Path, default=Path("data/output"))
    args = parser.parse_args()

    raw, truth = generate(args.seed, args.n_candidates)
    write_outputs(raw, truth, args.out, args.seed)
    for batch_id, batch in raw.groupby("batch_id"):
        print(f"{batch_id}: {len(batch)} rows, {batch['candidate_id'].nunique()} candidates")
    print(f"Synthetic data written to {args.out}")


if __name__ == "__main__":
    main()
