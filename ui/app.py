"""Streamlit app: progression probability and calibration curve. All data are synthetic.

The app talks to the prediction API only. It does not import azml_market: the
allowed input values are read from the API's OpenAPI document, which is the
contract between the two services.

Run locally with: uv run streamlit run ui/app.py
"""

import os

import altair as alt
import pandas as pd
import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")
TIMEOUT = 60  # the first call for a version downloads the model from MLflow

st.set_page_config(page_title="Clinical progression (synthetic)", layout="wide")
st.title("Clinical progression probability")
st.warning(
    "Synthetic data. Models are trained on generated data with arbitrary coefficients: "
    "the probabilities below say nothing about real clinical progression."
)


@st.cache_data(ttl=300)
def feature_schema() -> dict:
    """Allowed values per input field, read from the API contract."""
    spec = requests.get(f"{API_URL}/openapi.json", timeout=TIMEOUT).json()
    return spec["components"]["schemas"]["TransitionFeatures"]["properties"]


def get(path: str):
    response = requests.get(f"{API_URL}{path}", timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def model_label(m: dict) -> str:
    tags = ", ".join(m["aliases"] + ([m["validation_status"]] if m["validation_status"] else []))
    return f"v{m['version']} {m['model_kind']}" + (f" ({tags})" if tags else "")


try:
    models = get("/models")
    schema = feature_schema()
except requests.RequestException as exc:
    st.error(f"Prediction API not reachable at {API_URL}: {exc}")
    st.stop()

# Model choice, champion by default.
with st.sidebar:
    st.header("Model")
    default = next((i for i, m in enumerate(models) if "champion" in m["aliases"]), 0)
    chosen = st.selectbox("Model version", models, index=default, format_func=model_label)
    st.caption(chosen["validation_reason"] or "")
    ref = "champion" if "champion" in chosen["aliases"] else chosen["version"]

left, right = st.columns(2)

with left:
    st.subheader("One transition")
    with st.form("transition"):
        inputs = {}
        for field, spec in schema.items():
            label = field.replace("_", " ").capitalize()
            if "enum" in spec:
                inputs[field] = st.selectbox(label, spec["enum"])
            elif spec.get("type") == "boolean":
                inputs[field] = st.checkbox(label)
        submitted = st.form_submit_button("Predict")

    if submitted:
        response = requests.post(
            f"{API_URL}/predict", params={"model": ref}, json={"transitions": [inputs]}, timeout=TIMEOUT
        )
        if response.ok:
            result = response.json()
            st.metric("Probability of moving to the next phase", f"{result['predictions'][0]['p_progress']:.1%}")
            st.caption(f"Model v{result['model_version']} ({result['model_kind']}), requested as {result['model_ref']!r}")
        else:
            st.error(f"API error {response.status_code}: {response.text}")

with right:
    st.subheader("Calibration on the test set")
    cal = get(f"/models/{chosen['version']}/calibration")
    curves = pd.concat(
        [
            pd.DataFrame(cal["model_curve"]).assign(curve=f"model v{cal['model_version']}"),
            pd.DataFrame(cal["truth_curve"]).assign(curve="truth p_true"),
        ]
    )
    diagonal = alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(strokeDash=[4, 4], color="grey").encode(
        x="x", y="y"
    )
    lines = (
        alt.Chart(curves)
        .mark_line(point=True)
        .encode(
            x=alt.X("mean_predicted", title="Mean predicted probability", scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("observed_rate", title="Observed progression rate", scale=alt.Scale(domain=[0, 1])),
            color=alt.Color("curve", title=None),
            tooltip=["curve", "bin_lower", "bin_upper", "mean_predicted", "observed_rate", "n"],
        )
    )
    st.altair_chart((diagonal + lines).properties(height=420), width="stretch")
    c1, c2, c3 = st.columns(3)
    c1.metric("Brier (model)", f"{cal['test_brier']:.4f}")
    c2.metric("Brier (truth p_true)", f"{cal['truth_oracle_brier']:.4f}")
    c3.metric("Spiegelhalter p", f"{cal['test_spiegelhalter_p']:.3f}")
    st.caption(
        "Points on the dashed diagonal mean predicted probabilities match observed rates. "
        "The truth curve uses the probabilities the data were generated from."
    )
