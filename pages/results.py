"""
MoleCopilot Results -- Browse, filter, compare, and export docking results.
"""

import sys
from pathlib import Path

# Add project root to path so core/ and components/ are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from components.database import (
    init_db,
    get_all_proteins,
    get_docking_runs,
    get_docking_run,
    get_all_compounds,
)
from components.charts import energy_bar_chart, energy_histogram

# Ensure DB tables exist
init_db()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="MoleCopilot -- Results",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Results Browser")
st.caption("Browse, filter, compare, and export docking results.")

# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------


@st.cache_data(ttl=15)
def load_proteins() -> list[dict]:
    try:
        return get_all_proteins()
    except Exception as exc:
        st.error(f"Failed to load proteins: {exc}")
        return []


@st.cache_data(ttl=15)
def load_runs(protein_id=None, energy_min=None, energy_max=None, limit=200) -> list[dict]:
    try:
        return get_docking_runs(
            protein_id=protein_id,
            energy_min=energy_min,
            energy_max=energy_max,
            limit=limit,
        )
    except Exception as exc:
        st.error(f"Failed to load docking runs: {exc}")
        return []


@st.cache_data(ttl=15)
def load_run_detail(run_id: int) -> dict | None:
    try:
        return get_docking_run(run_id)
    except Exception as exc:
        st.error(f"Failed to load run #{run_id}: {exc}")
        return None


@st.cache_data(ttl=15)
def load_compounds() -> list[dict]:
    try:
        return get_all_compounds()
    except Exception as exc:
        st.error(f"Failed to load compounds: {exc}")
        return []


# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Filters")

    # Protein filter
    proteins = load_proteins()
    protein_options = {p["pdb_id"]: p["id"] for p in proteins}
    protein_labels = ["All Proteins"] + list(protein_options.keys())
    selected_protein_label = st.selectbox("Protein", protein_labels)

    selected_protein_id = None
    if selected_protein_label != "All Proteins":
        selected_protein_id = protein_options.get(selected_protein_label)

    # Energy range filter
    st.markdown("**Energy Range (kcal/mol)**")
    energy_range = st.slider(
        "Binding energy range",
        min_value=-15.0,
        max_value=0.0,
        value=(-15.0, 0.0),
        step=0.5,
        label_visibility="collapsed",
    )

    # Limit
    result_limit = st.number_input(
        "Max results",
        min_value=10,
        max_value=500,
        value=100,
        step=10,
    )

    st.divider()

    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# Load filtered data
# ---------------------------------------------------------------------------

runs = load_runs(
    protein_id=selected_protein_id,
    energy_min=energy_range[0],
    energy_max=energy_range[1],
    limit=result_limit,
)

if not runs:
    st.info(
        "No docking runs match the current filters. "
        "Try adjusting the sidebar filters or run a docking job first."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------

st.subheader(f"Docking Runs ({len(runs)} results)")

df = pd.DataFrame(runs)

# Build display DataFrame
display_map = {
    "id": "Run ID",
    "protein_pdb_id": "Protein",
    "compound_name": "Compound",
    "compound_smiles": "SMILES",
    "best_energy": "Energy (kcal/mol)",
    "exhaustiveness": "Exh.",
    "created_at": "Date",
}
available = [c for c in display_map if c in df.columns]
df_display = df[available].rename(columns=display_map)

# Format energy
if "Energy (kcal/mol)" in df_display.columns:
    df_display["Energy (kcal/mol)"] = df_display["Energy (kcal/mol)"].apply(
        lambda x: round(float(x), 2) if x is not None else None
    )

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Run ID": st.column_config.NumberColumn(width="small"),
        "SMILES": st.column_config.TextColumn(width="large"),
    },
)

# ---------------------------------------------------------------------------
# Visualization tabs
# ---------------------------------------------------------------------------

tab_chart, tab_hist, tab_detail, tab_compare = st.tabs(
    ["Bar Chart", "Distribution", "Run Details", "Compare"]
)

# -- Tab 1: Bar chart -------------------------------------------------------
with tab_chart:
    try:
        fig = energy_bar_chart(runs)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.error(f"Bar chart failed: {exc}")

# -- Tab 2: Histogram -------------------------------------------------------
with tab_hist:
    try:
        fig = energy_histogram(runs)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.error(f"Histogram failed: {exc}")

# -- Tab 3: Run detail -------------------------------------------------------
with tab_detail:
    run_ids = [r["id"] for r in runs]
    if run_ids:
        selected_run_id = st.selectbox(
            "Select a run to view details",
            options=run_ids,
            format_func=lambda rid: (
                f"Run #{rid} -- "
                + next(
                    (
                        f"{r['compound_name']} / {r['protein_pdb_id']} "
                        f"({r['best_energy']:.2f} kcal/mol)"
                        for r in runs
                        if r["id"] == rid
                    ),
                    str(rid),
                )
            ),
        )

        detail = load_run_detail(selected_run_id)
        if detail:
            det_col1, det_col2 = st.columns(2)

            with det_col1:
                st.markdown("**Docking Info**")
                st.write(f"- **Protein:** {detail.get('protein_pdb_id', 'N/A')} -- {detail.get('protein_title', '')}")
                st.write(f"- **Compound:** {detail.get('compound_name', 'N/A')}")
                st.write(f"- **SMILES:** `{detail.get('compound_smiles', 'N/A')}`")
                st.write(f"- **Best Energy:** {detail.get('best_energy', 'N/A')} kcal/mol")
                st.write(f"- **Exhaustiveness:** {detail.get('exhaustiveness', 'N/A')}")
                st.write(f"- **Date:** {detail.get('created_at', 'N/A')}")

                # Grid box info
                st.markdown("**Search Box**")
                st.write(
                    f"- Centre: ({detail.get('center_x', 0):.1f}, "
                    f"{detail.get('center_y', 0):.1f}, "
                    f"{detail.get('center_z', 0):.1f})"
                )
                st.write(
                    f"- Size: ({detail.get('size_x', 0):.1f}, "
                    f"{detail.get('size_y', 0):.1f}, "
                    f"{detail.get('size_z', 0):.1f})"
                )

            with det_col2:
                # All energies
                all_energies = detail.get("all_energies_json")
                if isinstance(all_energies, list) and all_energies:
                    st.markdown("**All Pose Energies**")
                    pose_df = pd.DataFrame(
                        {
                            "Pose": list(range(1, len(all_energies) + 1)),
                            "Energy (kcal/mol)": [f"{e:.2f}" for e in all_energies],
                        }
                    )
                    st.dataframe(pose_df, use_container_width=True, hide_index=True)

                # ADMET summary
                admet = detail.get("admet_json")
                if isinstance(admet, dict) and admet:
                    st.markdown("**ADMET Summary**")
                    score = admet.get("drug_likeness_score", "N/A")
                    assessment = admet.get("assessment", "N/A")
                    st.write(f"- Drug-likeness score: **{score}**")
                    st.write(f"- Assessment: **{assessment}**")

                    lip = admet.get("lipinski", {})
                    st.write(
                        f"- Lipinski: MW={lip.get('mw')}, LogP={lip.get('logp')}, "
                        f"HBD={lip.get('hbd')}, HBA={lip.get('hba')}, "
                        f"violations={lip.get('violations')}"
                    )

                    sa_score = admet.get("sa_score", "N/A")
                    sa_assess = admet.get("synthetic_assessment", "N/A")
                    if sa_score != "N/A":
                        st.write(f"- SA Score: **{sa_score:.1f}** ({sa_assess})")

                # Drug-likeness score metric + SA Score metric
                dl_score = detail.get("drug_likeness_score")
                sa_data = (detail.get("admet_json") or {}).get("sa_score")
                if dl_score is not None or sa_data is not None:
                    metric_cols = st.columns(2)
                    if dl_score is not None:
                        metric_cols[0].metric("Drug-Likeness Score", f"{dl_score:.2f}")
                    else:
                        metric_cols[0].metric("Drug-Likeness Score", "N/A")
                    if sa_data is not None:
                        sa_assess_label = (detail.get("admet_json") or {}).get("synthetic_assessment", "N/A")
                        metric_cols[1].metric(
                            "SA Score",
                            f"{sa_data:.1f}" if isinstance(sa_data, (int, float)) else sa_data,
                            delta=sa_assess_label,
                            delta_color="off",
                        )
                    else:
                        metric_cols[1].metric("SA Score", "N/A")

            # File paths
            with st.expander("Output Files"):
                st.code(f"Docked output: {detail.get('output_path', 'N/A')}")
                st.code(f"Protein PDB:   {detail.get('protein_pdb_path', 'N/A')}")
                st.code(f"Protein PDBQT: {detail.get('protein_pdbqt_path', 'N/A')}")

            # Interactions (if available)
            interactions = detail.get("interactions_json")
            if isinstance(interactions, dict) and interactions:
                with st.expander("Protein-Ligand Interactions"):
                    for itype, ilist in interactions.items():
                        if isinstance(ilist, list) and ilist:
                            st.markdown(f"**{itype.replace('_', ' ').title()}** ({len(ilist)})")
                            st.json(ilist)

        else:
            st.warning("Could not load details for this run.")

# -- Tab 4: Compare ----------------------------------------------------------
with tab_compare:
    st.markdown(
        "Select multiple runs to compare side-by-side. "
        "Pick runs from the list below."
    )

    run_labels = {
        r["id"]: (
            f"#{r['id']} -- {r.get('compound_name', 'Unknown')} / "
            f"{r.get('protein_pdb_id', '?')} ({r['best_energy']:.2f})"
        )
        for r in runs
    }

    selected_compare_ids = st.multiselect(
        "Runs to compare",
        options=list(run_labels.keys()),
        format_func=lambda x: run_labels[x],
        max_selections=8,
    )

    if len(selected_compare_ids) >= 2:
        compare_data = []
        for rid in selected_compare_ids:
            d = load_run_detail(rid)
            if d:
                compare_data.append(d)

        if compare_data:
            # Side-by-side metrics
            compare_cols = st.columns(len(compare_data))
            for idx, (col, run) in enumerate(zip(compare_cols, compare_data)):
                with col:
                    st.markdown(f"**#{run['id']}**")
                    st.write(f"Compound: {run.get('compound_name', 'N/A')}")
                    st.write(f"Protein: {run.get('protein_pdb_id', 'N/A')}")
                    st.metric(
                        "Energy",
                        f"{run.get('best_energy', 0):.2f}",
                    )
                    dl = run.get("drug_likeness_score")
                    if dl is not None:
                        st.metric("Drug-Likeness", f"{dl:.2f}")
                    else:
                        st.metric("Drug-Likeness", "N/A")
                    run_admet = run.get("admet_json") or {}
                    run_sa = run_admet.get("sa_score", "N/A")
                    run_sa_label = run_admet.get("synthetic_assessment", "N/A")
                    st.metric(
                        "SA Score",
                        f"{run_sa:.1f}" if isinstance(run_sa, (int, float)) else run_sa,
                        delta=run_sa_label if run_sa != "N/A" else None,
                        delta_color="off",
                    )

            # Comparison bar chart
            st.subheader("Energy Comparison")
            compare_chart_data = [
                {
                    "compound_name": f"#{r['id']} {r.get('compound_name', '?')}",
                    "best_energy": r.get("best_energy", 0),
                }
                for r in compare_data
            ]
            try:
                fig = energy_bar_chart(compare_chart_data)
                st.plotly_chart(fig, use_container_width=True)
            except Exception as exc:
                st.error(f"Comparison chart failed: {exc}")

    elif len(selected_compare_ids) == 1:
        st.info("Select at least 2 runs to compare.")
    else:
        st.info("Use the multiselect above to choose runs for comparison.")

# ---------------------------------------------------------------------------
# Export section
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Export")

export_col1, export_col2 = st.columns(2)

with export_col1:
    # CSV download
    csv_data = df_display.to_csv(index=False)
    st.download_button(
        label="Download Results CSV",
        data=csv_data,
        file_name="molecopilot_docking_results.csv",
        mime="text/csv",
        use_container_width=True,
    )

with export_col2:
    # DOCX report generation
    if st.button("Generate DOCX Report", use_container_width=True):
        try:
            from core.export_docs import export_docx

            # Build Markdown report content
            md_lines = [
                "# MoleCopilot Docking Results Report\n",
                f"**Total runs:** {len(runs)}\n",
                f"**Protein filter:** {selected_protein_label}\n",
                f"**Energy range:** {energy_range[0]} to {energy_range[1]} kcal/mol\n\n",
                "## Results\n\n",
                "| Rank | Compound | Protein | Energy (kcal/mol) | Date |",
                "|------|----------|---------|-------------------|------|",
            ]
            for rank, r in enumerate(runs, 1):
                cname = r.get("compound_name", "Unknown")
                prot = r.get("protein_pdb_id", "?")
                energy = r.get("best_energy")
                energy_str = f"{energy:.2f}" if energy is not None else "N/A"
                date = r.get("created_at", "N/A")
                md_lines.append(
                    f"| {rank} | {cname} | {prot} | {energy_str} | {date} |"
                )

            md_text = "\n".join(md_lines)

            docx_path = export_docx(
                markdown_text=md_text,
                title="MoleCopilot Docking Results",
            )
            st.success(f"Report generated: `{docx_path}`")

            # Offer download
            report_file = Path(docx_path)
            if report_file.is_file():
                with open(docx_path, "rb") as f:
                    st.download_button(
                        label="Download DOCX",
                        data=f.read(),
                        file_name=report_file.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
        except Exception as exc:
            st.error(f"Report generation failed: {exc}")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption("MoleCopilot -- Results Browser. Filter, compare, and export docking data.")
