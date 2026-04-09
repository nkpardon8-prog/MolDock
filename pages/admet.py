"""
MoleCopilot ADMET -- Drug-likeness and ADMET property checker.
"""

import sys
from pathlib import Path

# Add project root to path so core/ and components/ are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from components.database import init_db, save_compound, get_all_compounds
from components.charts import admet_radar

# Ensure DB tables exist
init_db()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="MoleCopilot -- ADMET",
    page_icon="💊",
    layout="wide",
)

st.title("💊 ADMET / Drug-Likeness Checker")
st.caption(
    "Evaluate Lipinski Rule-of-Five, Veber oral bioavailability, and "
    "combined drug-likeness scoring for any compound."
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "admet_result": None,
    "admet_smiles": None,
    "admet_name": None,
    "admet_batch_results": None,
}
for key, val in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------


@st.cache_data(ttl=30)
def load_compounds() -> list[dict]:
    try:
        return get_all_compounds()
    except Exception as exc:
        st.error(f"Failed to load compounds: {exc}")
        return []


# ---------------------------------------------------------------------------
# Tabs: Single check / Batch mode / Compare from DB
# ---------------------------------------------------------------------------

tab_single, tab_batch, tab_compare = st.tabs(
    ["Single Compound", "Batch Mode", "Compare from Database"]
)

# =====================================================================
# TAB 1: Single compound check
# =====================================================================
with tab_single:
    st.subheader("Check a Single Compound")

    single_col1, single_col2 = st.columns([2, 1])

    with single_col1:
        compound_input = st.text_input(
            "SMILES or compound name",
            value="",
            placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O  or  aspirin",
            help=(
                "Enter a SMILES string directly, or a compound name. "
                "Names will be resolved through PubChem."
            ),
            key="admet_single_input",
        )

    with single_col2:
        st.write("")  # Vertical spacer
        st.write("")
        check_clicked = st.button(
            "🔍 Check",
            use_container_width=True,
            type="primary",
            key="admet_single_check",
        )

    if check_clicked and compound_input.strip():
        compound_input = compound_input.strip()

        with st.spinner("Running ADMET analysis..."):
            smiles = None
            compound_name = compound_input

            # Step 1: Resolve input to SMILES
            try:
                from core.utils import validate_smiles

                if validate_smiles(compound_input):
                    smiles = compound_input
                    compound_name = compound_input[:40]
                else:
                    # Search PubChem by name
                    from core.fetch_compounds import search_pubchem

                    results = search_pubchem(compound_input, max_results=1)
                    if results:
                        hit = results[0]
                        smiles = hit["smiles"]
                        compound_name = hit.get("iupac_name") or compound_input
                        st.info(
                            f"Resolved '{compound_input}' via PubChem "
                            f"(CID {hit['cid']}): `{smiles[:80]}`"
                        )
                    else:
                        st.error(
                            f"Could not find '{compound_input}' on PubChem. "
                            "Try entering a SMILES string instead."
                        )
                        st.stop()
            except Exception as exc:
                st.error(f"Compound resolution failed: {exc}")
                st.stop()

            # Step 2: Run full ADMET
            try:
                from core.admet_check import full_admet

                admet_result = full_admet(smiles)
                st.session_state.admet_result = admet_result
                st.session_state.admet_smiles = smiles
                st.session_state.admet_name = compound_name
            except Exception as exc:
                st.error(f"ADMET check failed: {exc}")
                st.stop()

            # Step 3: Save to database
            try:
                save_compound(
                    name=compound_name,
                    smiles=smiles,
                    admet_data=admet_result,
                )
            except Exception as exc:
                st.warning(f"Database save failed (non-fatal): {exc}")

    elif check_clicked:
        st.warning("Please enter a SMILES string or compound name.")

    # Display results (persistent via session_state)
    admet_result = st.session_state.admet_result
    smiles = st.session_state.admet_smiles
    compound_name = st.session_state.admet_name

    if admet_result and admet_result.get("valid"):
        st.divider()

        # Assessment header
        score = admet_result["drug_likeness_score"]
        assessment = admet_result["assessment"]

        score_col1, score_col2, score_col3, score_col4 = st.columns(4)
        score_col1.metric("Drug-Likeness Score", f"{score:.2f}")
        score_col2.metric("Assessment", assessment)
        score_col3.metric("SMILES", smiles[:50] + ("..." if len(smiles) > 50 else ""))
        sa_score = admet_result.get("sa_score", "N/A")
        sa_label = admet_result.get("synthetic_assessment", "N/A")
        score_col4.metric(
            "SA Score",
            f"{sa_score:.1f}" if isinstance(sa_score, (int, float)) else sa_score,
            delta=sa_label,
            delta_color="off",
        )

        # Main content: properties table + radar chart
        prop_col, radar_col = st.columns([1, 1])

        with prop_col:
            st.markdown("### Property Table")

            # Lipinski properties
            lip = admet_result["lipinski"]
            veb = admet_result["veber"]

            properties = pd.DataFrame([
                {
                    "Property": "Molecular Weight",
                    "Value": lip["mw"],
                    "Rule": "Lipinski",
                    "Threshold": "<= 500",
                    "Status": "Pass" if lip["mw"] <= 500 else "FAIL",
                },
                {
                    "Property": "LogP",
                    "Value": lip["logp"],
                    "Rule": "Lipinski",
                    "Threshold": "<= 5",
                    "Status": "Pass" if lip["logp"] <= 5 else "FAIL",
                },
                {
                    "Property": "H-Bond Donors",
                    "Value": lip["hbd"],
                    "Rule": "Lipinski",
                    "Threshold": "<= 5",
                    "Status": "Pass" if lip["hbd"] <= 5 else "FAIL",
                },
                {
                    "Property": "H-Bond Acceptors",
                    "Value": lip["hba"],
                    "Rule": "Lipinski",
                    "Threshold": "<= 10",
                    "Status": "Pass" if lip["hba"] <= 10 else "FAIL",
                },
                {
                    "Property": "Rotatable Bonds",
                    "Value": veb["rotatable_bonds"],
                    "Rule": "Veber",
                    "Threshold": "<= 10",
                    "Status": "Pass" if veb["rotatable_bonds"] <= 10 else "FAIL",
                },
                {
                    "Property": "TPSA",
                    "Value": veb["tpsa"],
                    "Rule": "Veber",
                    "Threshold": "<= 140",
                    "Status": "Pass" if veb["tpsa"] <= 140 else "FAIL",
                },
                {
                    "Property": "Rings",
                    "Value": admet_result.get("num_rings", "N/A"),
                    "Rule": "--",
                    "Threshold": "--",
                    "Status": "--",
                },
                {
                    "Property": "Aromatic Rings",
                    "Value": admet_result.get("num_aromatic_rings", "N/A"),
                    "Rule": "--",
                    "Threshold": "--",
                    "Status": "--",
                },
                {
                    "Property": "Fraction Csp3",
                    "Value": admet_result.get("fraction_csp3", "N/A"),
                    "Rule": "--",
                    "Threshold": "> 0.25 preferred",
                    "Status": (
                        "Pass"
                        if admet_result.get("fraction_csp3", 0) > 0.25
                        else "Low"
                    ),
                },
                {
                    "Property": "Molar Refractivity",
                    "Value": admet_result.get("molar_refractivity", "N/A"),
                    "Rule": "--",
                    "Threshold": "40-130",
                    "Status": "--",
                },
                {
                    "Property": "Heavy Atoms",
                    "Value": admet_result.get("num_heavy_atoms", "N/A"),
                    "Rule": "--",
                    "Threshold": "--",
                    "Status": "--",
                },
                {
                    "Property": "SA Score",
                    "Value": admet_result.get("sa_score", "N/A"),
                    "Rule": "--",
                    "Threshold": "1 (easy) - 10 (hard)",
                    "Status": admet_result.get("synthetic_assessment", "N/A"),
                },
            ])

            st.dataframe(
                properties,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Status": st.column_config.TextColumn(width="small"),
                },
            )

        with radar_col:
            st.markdown("### Radar Chart")
            try:
                fig = admet_radar(admet_result, compound_name=compound_name or "Compound")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as exc:
                st.error(f"Radar chart failed: {exc}")

        # 2D structure image
        st.markdown("### 2D Structure")
        try:
            from core.generate_figures import draw_molecule_2d

            img_path = draw_molecule_2d(smiles, name=compound_name)
            if img_path and Path(img_path).is_file():
                st.image(img_path, caption=compound_name or "Compound", width=400)
        except Exception as exc:
            st.warning(f"2D structure rendering failed: {exc}")

    elif admet_result and not admet_result.get("valid"):
        st.error("Invalid SMILES string. Please check the input and try again.")


# =====================================================================
# TAB 2: Batch mode
# =====================================================================
with tab_batch:
    st.subheader("Batch ADMET Check")
    st.markdown(
        "Enter multiple SMILES strings, one per line. "
        "Optionally add a name after a comma: `SMILES,name`"
    )

    batch_input = st.text_area(
        "SMILES list (one per line)",
        height=200,
        placeholder=(
            "CC(=O)Oc1ccccc1C(=O)O, aspirin\n"
            "Cn1c(=O)c2c(ncn2C)n(C)c1=O, caffeine\n"
            "CC12CCC3C(C1CCC2=O)CC(=C)C4=CC(=O)C=CC34C, exemestane"
        ),
        key="admet_batch_input",
    )

    batch_clicked = st.button(
        "🔬 Run Batch ADMET",
        use_container_width=True,
        type="primary",
        key="admet_batch_check",
    )

    if batch_clicked and batch_input.strip():
        lines = [l.strip() for l in batch_input.strip().splitlines() if l.strip()]

        smiles_list = []
        names_list = []

        for line in lines:
            if "," in line:
                parts = line.split(",", 1)
                smiles_list.append(parts[0].strip())
                names_list.append(parts[1].strip())
            else:
                smiles_list.append(line.strip())
                names_list.append(f"Compound_{len(smiles_list)}")

        if not smiles_list:
            st.warning("No valid SMILES found in the input.")
        else:
            with st.spinner(f"Checking {len(smiles_list)} compounds..."):
                try:
                    from core.admet_check import batch_admet

                    batch_result = batch_admet(smiles_list, names_list)
                    st.session_state.admet_batch_results = batch_result["results"]
                    st.success(batch_result["summary"])

                    # Save each to DB
                    for r in batch_result["results"]:
                        try:
                            save_compound(
                                name=r.get("name"),
                                smiles=r.get("smiles"),
                                admet_data=r,
                            )
                        except Exception:
                            pass  # Non-fatal

                except Exception as exc:
                    st.error(f"Batch ADMET failed: {exc}")

    elif batch_clicked:
        st.warning("Please enter at least one SMILES string.")

    # Display batch results
    batch_results = st.session_state.admet_batch_results

    if batch_results:
        st.divider()

        # Summary table
        batch_df = pd.DataFrame([
            {
                "Name": r.get("name", ""),
                "SMILES": r.get("smiles", ""),
                "MW": r.get("mw"),
                "LogP": r.get("logp"),
                "HBD": r.get("hbd"),
                "HBA": r.get("hba"),
                "RotBonds": r.get("rotatable_bonds"),
                "TPSA": r.get("tpsa"),
                "Score": r.get("drug_likeness_score"),
                "Assessment": r.get("assessment"),
                "SA Score": r.get("sa_score", "N/A"),
                "Synth.": r.get("synthetic_assessment", "N/A"),
            }
            for r in batch_results
        ])

        st.dataframe(
            batch_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "SMILES": st.column_config.TextColumn(width="large"),
                "Score": st.column_config.ProgressColumn(
                    min_value=0.0,
                    max_value=1.0,
                    format="%.2f",
                ),
            },
        )

        # Download CSV
        csv_data = batch_df.to_csv(index=False)
        st.download_button(
            label="Download Batch Results CSV",
            data=csv_data,
            file_name="molecopilot_admet_batch.csv",
            mime="text/csv",
            use_container_width=True,
        )

        # Individual radar charts in expanders
        for r in batch_results:
            with st.expander(
                f"{r.get('name', 'Compound')} -- {r.get('assessment', 'N/A')} "
                f"(score: {r.get('drug_likeness_score', 0):.2f})"
            ):
                try:
                    fig = admet_radar(r, compound_name=r.get("name", "Compound"))
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as exc:
                    st.error(f"Radar chart failed: {exc}")


# =====================================================================
# TAB 3: Compare from database
# =====================================================================
with tab_compare:
    st.subheader("Compare Compounds from Database")
    st.markdown(
        "Select compounds that have been previously checked and compare "
        "their ADMET profiles side-by-side."
    )

    compounds = load_compounds()

    if not compounds:
        st.info(
            "No compounds in the database yet. "
            "Run an ADMET check or docking job first."
        )
    else:
        # Build selection options
        compound_options = {}
        for c in compounds:
            label = f"{c.get('name', 'Unknown')} (id={c['id']})"
            if c.get("smiles"):
                label += f" -- {c['smiles'][:40]}"
            compound_options[c["id"]] = label

        selected_ids = st.multiselect(
            "Select compounds to compare",
            options=list(compound_options.keys()),
            format_func=lambda x: compound_options[x],
            max_selections=6,
            key="admet_compare_select",
        )

        if len(selected_ids) >= 2:
            selected_compounds = [c for c in compounds if c["id"] in selected_ids]

            # Side-by-side metrics
            metric_cols = st.columns(len(selected_compounds))
            for col, comp in zip(metric_cols, selected_compounds):
                with col:
                    st.markdown(f"**{comp.get('name', 'Unknown')}**")
                    admet = comp.get("admet_json")
                    if isinstance(admet, dict):
                        st.metric(
                            "Score",
                            f"{admet.get('drug_likeness_score', 0):.2f}",
                        )
                        st.write(f"Assessment: {admet.get('assessment', 'N/A')}")
                        st.write(f"MW: {admet.get('mw', 'N/A')}")
                        st.write(f"LogP: {admet.get('logp', 'N/A')}")
                    else:
                        dl = comp.get("drug_likeness_score")
                        if dl is not None:
                            st.metric("Score", f"{dl:.2f}")
                        else:
                            st.metric("Score", "N/A")

            # Overlay radar chart
            st.markdown("### ADMET Radar Overlay")

            # Build traces for overlay
            import plotly.graph_objects as go

            categories = ["MW", "LogP", "HBD", "HBA", "RotBonds", "TPSA"]
            max_vals = [500, 5, 5, 10, 10, 140]
            trace_colors = [
                "#00D4AA", "#FF4B4B", "#FFD700", "#9b59b6",
                "#3498db", "#e67e22",
            ]

            fig = go.Figure()

            # Ideal limit trace
            fig.add_trace(go.Scatterpolar(
                r=[1.0] * 6 + [1.0],
                theta=categories + [categories[0]],
                fill="toself",
                fillcolor="rgba(0, 212, 170, 0.05)",
                line=dict(color="rgba(0, 212, 170, 0.3)", dash="dash", width=1),
                name="Ideal Limit",
                hoverinfo="skip",
            ))

            for idx, comp in enumerate(selected_compounds):
                name = comp.get("name", f"Compound {idx + 1}")
                admet = comp.get("admet_json", {})
                if not isinstance(admet, dict):
                    admet = {}

                raw = [
                    admet.get("mw", 0) or 0,
                    admet.get("logp", 0) or 0,
                    admet.get("hbd", 0) or 0,
                    admet.get("hba", 0) or 0,
                    admet.get("rotatable_bonds", 0) or 0,
                    admet.get("tpsa", 0) or 0,
                ]
                normalized = [
                    min(float(v) / m, 1.5) if m else 0
                    for v, m in zip(raw, max_vals)
                ]

                color = trace_colors[idx % len(trace_colors)]
                fig.add_trace(go.Scatterpolar(
                    r=normalized + [normalized[0]],
                    theta=categories + [categories[0]],
                    fill="toself",
                    fillcolor=f"rgba{_hex_to_rgba(color, 0.15)}",
                    line=dict(color=color, width=2),
                    name=name,
                    text=[
                        f"{c}: {r}" for c, r in zip(categories, raw)
                    ] + [f"{categories[0]}: {raw[0]}"],
                    hoverinfo="text",
                ))

            fig.update_layout(
                polar=dict(
                    bgcolor="rgba(0,0,0,0)",
                    radialaxis=dict(
                        visible=True,
                        range=[0, 1.2],
                        gridcolor="rgba(255,255,255,0.1)",
                    ),
                    angularaxis=dict(
                        gridcolor="rgba(255,255,255,0.15)",
                    ),
                ),
                title="ADMET Comparison Overlay",
                showlegend=True,
                height=550,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#FAFAFA"),
            )

            st.plotly_chart(fig, use_container_width=True)

            # Comparison table
            st.markdown("### Comparison Table")
            compare_df = pd.DataFrame([
                {
                    "Compound": comp.get("name", "Unknown"),
                    "SMILES": comp.get("smiles", ""),
                    "MW": (comp.get("admet_json") or {}).get("mw", "N/A"),
                    "LogP": (comp.get("admet_json") or {}).get("logp", "N/A"),
                    "HBD": (comp.get("admet_json") or {}).get("hbd", "N/A"),
                    "HBA": (comp.get("admet_json") or {}).get("hba", "N/A"),
                    "RotBonds": (comp.get("admet_json") or {}).get("rotatable_bonds", "N/A"),
                    "TPSA": (comp.get("admet_json") or {}).get("tpsa", "N/A"),
                    "Score": comp.get("drug_likeness_score", "N/A"),
                    "Assessment": (comp.get("admet_json") or {}).get("assessment", "N/A"),
                    "SA Score": (comp.get("admet_json") or {}).get("sa_score", "N/A"),
                    "Synth.": (comp.get("admet_json") or {}).get("synthetic_assessment", "N/A"),
                }
                for comp in selected_compounds
            ])
            st.dataframe(compare_df, use_container_width=True, hide_index=True)

        elif len(selected_ids) == 1:
            st.info("Select at least 2 compounds to compare.")
        else:
            st.info("Use the multiselect above to choose compounds for comparison.")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple:
    """Convert hex color to RGBA tuple for Plotly."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b, alpha)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "MoleCopilot -- ADMET Checker. Evaluates Lipinski Ro5, Veber rules, "
    "and combined drug-likeness scoring."
)
