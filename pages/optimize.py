"""
MoleCopilot Optimize -- MolMIM AI-powered molecular generation and optimization.
"""

import sys
from pathlib import Path

# Add project root to path so core/ and components/ are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from components.database import init_db, save_compound
from components.charts import admet_radar

# Ensure DB tables exist
init_db()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="MoleCopilot -- Optimize",
    page_icon="\U0001f9ea",
    layout="wide",
)

st.title("\U0001f9ea Optimize Compound")
st.caption(
    "Generate optimized molecular analogs using NVIDIA MolMIM AI. "
    "CMA-ES evolutionary strategy explores chemical space while maintaining "
    "similarity to the seed compound."
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "optimize_result": None,
    "optimize_seed": None,
}
for key, val in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------------------------------------------------------------------------
# Helper: hex to rgba tuple (matches admet.py pattern)
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
# Input form
# ---------------------------------------------------------------------------

with st.form("optimize_form"):
    st.subheader("Optimization Parameters")

    form_col1, form_col2 = st.columns(2)

    with form_col1:
        compound_input = st.text_input(
            "Compound (SMILES or name)",
            value="",
            placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O  or  aspirin",
            help=(
                "Enter a SMILES string directly, or a compound name. "
                "Names will be resolved through PubChem."
            ),
        )

        opt_property = st.selectbox(
            "Optimization Property",
            options=["QED", "plogP"],
            index=0,
            help=(
                "QED: Quantitative Estimate of Drug-likeness (0-1, higher is better). "
                "plogP: Penalized LogP (higher values indicate better lipophilicity)."
            ),
        )

    with form_col2:
        num_molecules = st.slider(
            "Number of Molecules",
            min_value=5,
            max_value=50,
            value=20,
            step=5,
            help="Number of optimized analogs to generate.",
        )

        min_similarity = st.slider(
            "Minimum Similarity",
            min_value=0.0,
            max_value=0.7,
            value=0.3,
            step=0.05,
            help=(
                "Minimum Tanimoto similarity to the seed compound. "
                "Higher values keep analogs closer to the original structure."
            ),
        )

    submitted = st.form_submit_button(
        "\u2728 Generate Optimized Analogs",
        use_container_width=True,
        type="primary",
    )

# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

if submitted:
    # Validate input
    if not compound_input.strip():
        st.error("Please enter a compound SMILES or name.")
        st.stop()

    compound_input = compound_input.strip()

    with st.status("Running optimization pipeline...", expanded=True) as status:
        # ==================================================================
        # Step 1: Resolve compound input
        # ==================================================================
        st.write("**Step 1/5:** Resolving compound...")

        smiles = None
        compound_name = compound_input

        try:
            from core.utils import validate_smiles

            if validate_smiles(compound_input):
                smiles = compound_input
                compound_name = compound_input[:40]
                st.write(f"  Input recognised as SMILES: `{smiles[:60]}`")
            else:
                # Search PubChem by name
                st.write(f"  Searching PubChem for '{compound_input}'...")
                from core.fetch_compounds import search_pubchem

                results = search_pubchem(compound_input, max_results=1)
                if not results:
                    st.error(
                        f"No compounds found on PubChem for '{compound_input}'. "
                        "Try entering a SMILES string instead."
                    )
                    status.update(label="Pipeline failed at Step 1", state="error")
                    st.stop()

                hit = results[0]
                smiles = hit.get("smiles", "")
                compound_name = hit.get("iupac_name") or compound_input

                if not smiles:
                    st.error(
                        f"PubChem returned no SMILES for '{compound_input}' "
                        f"(CID {hit.get('cid')}). Try entering the SMILES directly."
                    )
                    status.update(label="Pipeline failed at Step 1", state="error")
                    st.stop()

                st.write(
                    f"  Found: **{compound_input}** (CID {hit['cid']}) -- "
                    f"SMILES: `{smiles[:60]}`"
                )
        except Exception as exc:
            st.error(f"Compound resolution failed: {exc}")
            status.update(label="Pipeline failed at Step 1", state="error")
            st.stop()

        # ==================================================================
        # Step 2: Baseline ADMET on seed compound
        # ==================================================================
        st.write("**Step 2/5:** Running baseline ADMET on seed compound...")
        try:
            from core.admet_check import full_admet

            seed_admet = full_admet(smiles)
            st.write(
                f"  Seed assessment: **{seed_admet['assessment']}** "
                f"(score: {seed_admet['drug_likeness_score']:.2f}, "
                f"SA: {seed_admet['sa_score']:.1f})"
            )
        except Exception as exc:
            st.warning(f"Baseline ADMET failed (non-fatal): {exc}")
            seed_admet = None

        # ==================================================================
        # Step 3: Generate optimized analogs via MolMIM
        # ==================================================================
        st.write("**Step 3/5:** Generating optimized analogs with MolMIM AI...")
        try:
            from core.bionemo import optimize_molecules

            opt_result = optimize_molecules(
                smiles=smiles,
                property_name=opt_property,
                num_molecules=num_molecules,
                min_similarity=min_similarity,
            )
            st.write(
                f"  Generated **{opt_result['num_generated']}** unique analogs "
                f"via {opt_result['method']}"
            )
        except RuntimeError as exc:
            error_msg = str(exc)
            if "NVIDIA_API_KEY" in error_msg:
                st.error(
                    "NVIDIA API key not found. To use MolMIM molecular generation:\n\n"
                    "1. Sign up at [build.nvidia.com](https://build.nvidia.com/)\n"
                    "2. Generate an API key\n"
                    "3. Add `NVIDIA_API_KEY=your-key-here` to your `.env` file"
                )
            else:
                st.error(f"MolMIM API error: {exc}")
            status.update(label="Pipeline failed at Step 3", state="error")
            st.stop()
        except ValueError as exc:
            st.error(f"Invalid SMILES input: {exc}")
            status.update(label="Pipeline failed at Step 3", state="error")
            st.stop()
        except Exception as exc:
            st.error(f"Molecular generation failed: {exc}")
            status.update(label="Pipeline failed at Step 3", state="error")
            st.stop()

        # ==================================================================
        # Step 4: ADMET check on all analogs
        # ==================================================================
        st.write("**Step 4/5:** Running ADMET on generated analogs...")
        try:
            from core.admet_check import full_admet

            analogs_with_admet = []
            for i, analog in enumerate(opt_result["analogs"]):
                admet = full_admet(analog["smiles"])
                analogs_with_admet.append({
                    "smiles": analog["smiles"],
                    "property_score": analog["score"],
                    "admet": admet,
                })
            st.write(f"  ADMET completed for {len(analogs_with_admet)} analogs")
        except Exception as exc:
            st.error(f"ADMET analysis failed: {exc}")
            status.update(label="Pipeline failed at Step 4", state="error")
            st.stop()

        # ==================================================================
        # Step 5: Filter by SA score and save
        # ==================================================================
        st.write("**Step 5/5:** Filtering and saving results...")

        # Filter: remove analogs with SA score > 7
        passing_analogs = [
            a for a in analogs_with_admet
            if a["admet"].get("sa_score", 10.0) <= 7.0
        ]

        st.write(
            f"  {len(passing_analogs)} of {len(analogs_with_admet)} analogs "
            f"pass SA filter (SA <= 7.0)"
        )

        # Sort by property score descending
        passing_analogs.sort(key=lambda a: a["property_score"], reverse=True)

        # Store results in session state
        st.session_state.optimize_result = {
            "seed_smiles": smiles,
            "seed_name": compound_name,
            "seed_admet": seed_admet,
            "property": opt_property,
            "all_analogs": analogs_with_admet,
            "passing_analogs": passing_analogs,
            "num_generated": len(analogs_with_admet),
            "num_passing": len(passing_analogs),
        }
        st.session_state.optimize_seed = {
            "smiles": smiles,
            "name": compound_name,
            "admet": seed_admet,
        }

        # Save passing analogs to database
        saved_count = 0
        for analog in passing_analogs:
            try:
                save_compound(
                    name=f"{compound_name}_analog_{saved_count + 1}",
                    smiles=analog["smiles"],
                    admet_data=analog["admet"],
                )
                saved_count += 1
            except Exception:
                pass  # Non-fatal

        st.write(f"  Saved {saved_count} analogs to database")

        status.update(label="Optimization complete!", state="complete")

# ---------------------------------------------------------------------------
# Display results (persisted in session_state)
# ---------------------------------------------------------------------------

result = st.session_state.optimize_result

if result is not None:
    st.divider()
    st.subheader("Optimization Results")

    # ── Summary metrics row ───────────────────────────────────────────────
    met_col1, met_col2, met_col3, met_col4 = st.columns(4)

    met_col1.metric(
        "Generated",
        result["num_generated"],
        help="Total unique analogs returned by MolMIM",
    )
    met_col2.metric(
        "Passing SA Filter",
        result["num_passing"],
        help="Analogs with SA score <= 7.0 (synthesizable)",
    )

    passing = result["passing_analogs"]
    if passing:
        best_prop = max(a["property_score"] for a in passing)
        met_col3.metric(
            f"Best {result['property']}",
            f"{best_prop:.3f}",
            help=f"Highest {result['property']} score among passing analogs",
        )

        best_sa = min(a["admet"].get("sa_score", 10.0) for a in passing)
        met_col4.metric(
            "Best SA Score",
            f"{best_sa:.1f}",
            help="Lowest SA score (1 = easy to synthesize, 10 = very difficult)",
        )
    else:
        met_col3.metric(f"Best {result['property']}", "N/A")
        met_col4.metric("Best SA Score", "N/A")

    # ── Seed compound baseline ────────────────────────────────────────────
    seed_admet = result.get("seed_admet")
    if seed_admet and seed_admet.get("valid"):
        with st.expander("Seed Compound Baseline", expanded=False):
            seed_col1, seed_col2, seed_col3, seed_col4 = st.columns(4)
            seed_col1.metric("Compound", result["seed_name"][:30])
            seed_col2.metric(
                "Drug-Likeness",
                f"{seed_admet['drug_likeness_score']:.2f}",
            )
            seed_col3.metric("Assessment", seed_admet["assessment"])
            seed_col4.metric(
                "SA Score",
                f"{seed_admet['sa_score']:.1f}",
                help=seed_admet.get("synthetic_assessment", ""),
            )

            # ADMET table for seed
            lip = seed_admet["lipinski"]
            veb = seed_admet["veber"]
            seed_props = pd.DataFrame([
                {
                    "Property": "Molecular Weight",
                    "Value": lip["mw"],
                    "Threshold": "<= 500",
                    "Status": "Pass" if lip["mw"] <= 500 else "FAIL",
                },
                {
                    "Property": "LogP",
                    "Value": lip["logp"],
                    "Threshold": "<= 5",
                    "Status": "Pass" if lip["logp"] <= 5 else "FAIL",
                },
                {
                    "Property": "H-Bond Donors",
                    "Value": lip["hbd"],
                    "Threshold": "<= 5",
                    "Status": "Pass" if lip["hbd"] <= 5 else "FAIL",
                },
                {
                    "Property": "H-Bond Acceptors",
                    "Value": lip["hba"],
                    "Threshold": "<= 10",
                    "Status": "Pass" if lip["hba"] <= 10 else "FAIL",
                },
                {
                    "Property": "Rotatable Bonds",
                    "Value": veb["rotatable_bonds"],
                    "Threshold": "<= 10",
                    "Status": "Pass" if veb["rotatable_bonds"] <= 10 else "FAIL",
                },
                {
                    "Property": "TPSA",
                    "Value": veb["tpsa"],
                    "Threshold": "<= 140",
                    "Status": "Pass" if veb["tpsa"] <= 140 else "FAIL",
                },
                {
                    "Property": "SA Score",
                    "Value": seed_admet.get("sa_score", "N/A"),
                    "Threshold": "<= 7",
                    "Status": (
                        "Pass" if seed_admet.get("sa_score", 10) <= 7 else "FAIL"
                    ),
                },
            ])
            st.dataframe(
                seed_props,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Status": st.column_config.TextColumn(width="small"),
                },
            )

    # ── Results table ─────────────────────────────────────────────────────
    if passing:
        st.subheader("Optimized Analogs")

        table_data = []
        for rank, analog in enumerate(passing, 1):
            admet = analog["admet"]
            table_data.append({
                "Rank": rank,
                "SMILES": analog["smiles"],
                f"{result['property']} Score": round(analog["property_score"], 4),
                "SA Score": admet.get("sa_score", "N/A"),
                "SA Assessment": admet.get("synthetic_assessment", "N/A"),
                "MW": admet.get("mw", "N/A"),
                "LogP": admet.get("logp", "N/A"),
                "Drug-Likeness": (
                    f"{admet.get('drug_likeness_score', 0):.2f}"
                    if admet.get("drug_likeness_score") is not None
                    else "N/A"
                ),
                "Assessment": admet.get("assessment", "N/A"),
            })

        results_df = pd.DataFrame(table_data)
        st.dataframe(
            results_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "SMILES": st.column_config.TextColumn(width="large"),
                "Rank": st.column_config.NumberColumn(width="small"),
            },
        )

        # Download CSV
        csv_data = results_df.to_csv(index=False)
        st.download_button(
            label="Download Results CSV",
            data=csv_data,
            file_name="molecopilot_optimize_results.csv",
            mime="text/csv",
            use_container_width=True,
        )

        # ── Comparison charts ─────────────────────────────────────────────
        st.subheader("Comparison Charts")

        chart_col1, chart_col2 = st.columns(2)

        # Left: ADMET radar overlay of seed + top 3 analogs
        with chart_col1:
            st.markdown("### ADMET Radar Overlay")

            import plotly.graph_objects as go

            categories = ["MW", "LogP", "HBD", "HBA", "RotBonds", "TPSA"]
            max_vals = [500, 5, 5, 10, 10, 140]
            trace_colors = [
                "#FFD700",  # seed = gold
                "#00D4AA",  # analog 1 = teal
                "#FF4B4B",  # analog 2 = red
                "#9b59b6",  # analog 3 = purple
            ]

            fig_radar = go.Figure()

            # Ideal limit trace
            fig_radar.add_trace(go.Scatterpolar(
                r=[1.0] * 6 + [1.0],
                theta=categories + [categories[0]],
                fill="toself",
                fillcolor="rgba(0, 212, 170, 0.05)",
                line=dict(color="rgba(0, 212, 170, 0.3)", dash="dash", width=1),
                name="Ideal Limit",
                hoverinfo="skip",
            ))

            # Seed compound trace
            compounds_to_plot = []
            if seed_admet and seed_admet.get("valid"):
                compounds_to_plot.append(
                    (f"Seed: {result['seed_name'][:20]}", seed_admet)
                )

            # Top 3 analogs
            for i, analog in enumerate(passing[:3]):
                admet = analog["admet"]
                if admet.get("valid"):
                    compounds_to_plot.append(
                        (f"Analog {i + 1}", admet)
                    )

            for idx, (name, admet) in enumerate(compounds_to_plot):
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
                fig_radar.add_trace(go.Scatterpolar(
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

            fig_radar.update_layout(
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
                title="Seed vs Top Analogs",
                showlegend=True,
                height=500,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#FAFAFA"),
                margin=dict(l=20, r=20, t=40, b=20),
            )

            st.plotly_chart(fig_radar, use_container_width=True)

        # Right: Bar chart of SA scores for all analogs
        with chart_col2:
            st.markdown("### Synthetic Accessibility Scores")

            import plotly.graph_objects as go

            sa_scores = [a["admet"].get("sa_score", 10.0) for a in passing]
            labels = [f"Analog {i + 1}" for i in range(len(passing))]

            # Color coding: green <= 3, gold 3-5, orange 5-7
            sa_colors = []
            for sa in sa_scores:
                if sa <= 3:
                    sa_colors.append("#00D4AA")  # easy
                elif sa <= 5:
                    sa_colors.append("#FFD700")  # moderate
                else:
                    sa_colors.append("#FF8C00")  # difficult

            fig_sa = go.Figure()

            fig_sa.add_trace(
                go.Bar(
                    y=labels,
                    x=sa_scores,
                    orientation="h",
                    marker=dict(color=sa_colors, line=dict(width=0)),
                    text=[f"{s:.1f}" for s in sa_scores],
                    textposition="outside",
                    textfont=dict(color="#FAFAFA", size=11),
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "SA Score: %{x:.2f}<extra></extra>"
                    ),
                )
            )

            # Threshold line at SA = 5 (moderate/difficult boundary)
            fig_sa.add_vline(
                x=5.0,
                line_dash="dash",
                line_color="#FFD700",
                line_width=1.5,
                annotation_text="SA = 5",
                annotation_position="top",
                annotation_font_color="#FFD700",
                annotation_font_size=10,
            )

            fig_sa.update_layout(
                title=dict(
                    text="SA Scores (lower = easier to synthesize)",
                    font=dict(size=14),
                ),
                xaxis=dict(
                    title="SA Score",
                    gridcolor="rgba(255,255,255,0.1)",
                    range=[0, max(sa_scores) * 1.2 if sa_scores else 10],
                    zeroline=False,
                ),
                yaxis=dict(
                    title="",
                    autorange="reversed",
                    gridcolor="rgba(255,255,255,0.1)",
                ),
                height=max(300, len(labels) * 30 + 100),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#FAFAFA", family="sans-serif"),
                margin=dict(l=20, r=20, t=40, b=20),
            )

            st.plotly_chart(fig_sa, use_container_width=True)

        # ── Individual analog details ─────────────────────────────────────
        st.subheader("Individual Analog Details")

        for rank, analog in enumerate(passing, 1):
            admet = analog["admet"]
            sa_label = admet.get("synthetic_assessment", "N/A")
            score_label = admet.get("assessment", "N/A")

            with st.expander(
                f"Analog {rank} -- {score_label} "
                f"({result['property']}: {analog['property_score']:.4f}, "
                f"SA: {admet.get('sa_score', 'N/A')})"
            ):
                detail_col1, detail_col2 = st.columns([1, 1])

                with detail_col1:
                    st.markdown(f"**SMILES:** `{analog['smiles']}`")

                    if admet.get("valid"):
                        lip = admet["lipinski"]
                        veb = admet["veber"]

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
                                "Status": (
                                    "Pass"
                                    if veb["rotatable_bonds"] <= 10
                                    else "FAIL"
                                ),
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
                                "Value": admet.get("num_rings", "N/A"),
                                "Rule": "--",
                                "Threshold": "--",
                                "Status": "--",
                            },
                            {
                                "Property": "Aromatic Rings",
                                "Value": admet.get("num_aromatic_rings", "N/A"),
                                "Rule": "--",
                                "Threshold": "--",
                                "Status": "--",
                            },
                            {
                                "Property": "Fraction Csp3",
                                "Value": admet.get("fraction_csp3", "N/A"),
                                "Rule": "--",
                                "Threshold": "> 0.25 preferred",
                                "Status": (
                                    "Pass"
                                    if admet.get("fraction_csp3", 0) > 0.25
                                    else "Low"
                                ),
                            },
                            {
                                "Property": "SA Score",
                                "Value": admet.get("sa_score", "N/A"),
                                "Rule": "Synth.",
                                "Threshold": "<= 7",
                                "Status": (
                                    "Pass"
                                    if admet.get("sa_score", 10) <= 7
                                    else "FAIL"
                                ),
                            },
                        ])

                        st.dataframe(
                            properties,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Status": st.column_config.TextColumn(
                                    width="small"
                                ),
                            },
                        )

                with detail_col2:
                    if admet.get("valid"):
                        try:
                            fig = admet_radar(
                                admet,
                                compound_name=f"Analog {rank}",
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        except Exception as exc:
                            st.error(f"Radar chart failed: {exc}")

    else:
        st.warning(
            "No analogs passed the SA filter (SA score <= 7.0). "
            "Try increasing the number of molecules or adjusting the "
            "minimum similarity threshold."
        )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "MoleCopilot -- Optimize. Pipeline: resolve compound -> baseline ADMET -> "
    "MolMIM CMA-ES generation -> ADMET screening -> SA filtering."
)
