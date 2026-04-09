"""
MoleCopilot Dashboard -- Home page with overview stats and recent activity.
"""

import sys
from pathlib import Path

# Add project root to path so core/ and components/ are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from components.database import init_db, get_stats, get_recent_docking_runs
from components.charts import energy_bar_chart

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="MoleCopilot Dashboard",
    page_icon="🧬",
    layout="wide",
)

# Ensure DB tables exist on first load
init_db()

# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------


@st.cache_data(ttl=30)
def load_stats() -> dict:
    """Fetch summary statistics from the database."""
    try:
        return get_stats()
    except Exception as exc:
        st.error(f"Failed to load stats: {exc}")
        return {
            "total_proteins": 0,
            "total_compounds": 0,
            "total_runs": 0,
            "best_energy": None,
            "best_compound": None,
        }


@st.cache_data(ttl=30)
def load_recent_runs(limit: int = 10) -> list[dict]:
    """Fetch most recent docking runs."""
    try:
        return get_recent_docking_runs(limit)
    except Exception as exc:
        st.error(f"Failed to load recent runs: {exc}")
        return []


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

hdr_col1, hdr_col2 = st.columns([5, 1])
hdr_col1.title("MoleCopilot Dashboard")
hdr_col1.caption("Molecular docking research agent -- overview and recent activity")
if hdr_col2.button("Refresh", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# ---------------------------------------------------------------------------
# Stat cards (4 columns)
# ---------------------------------------------------------------------------

stats = load_stats()

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    label="Proteins",
    value=stats["total_proteins"],
    help="Total protein structures in the database",
)
col2.metric(
    label="Compounds",
    value=stats["total_compounds"],
    help="Total small molecules in the database",
)
col3.metric(
    label="Docking Runs",
    value=stats["total_runs"],
    help="Total docking jobs completed",
)
col4.metric(
    label="Best Energy",
    value=(
        f"{stats['best_energy']:.1f} kcal/mol"
        if stats["best_energy"] is not None
        else "N/A"
    ),
    help=(
        f"Best binding energy ({stats['best_compound']})"
        if stats["best_compound"]
        else "No docking runs yet"
    ),
)

st.divider()

# ---------------------------------------------------------------------------
# Recent docking runs table
# ---------------------------------------------------------------------------

st.subheader("Recent Docking Runs")

recent = load_recent_runs(10)

if recent:
    df = pd.DataFrame(recent)

    # Build a cleaner display table
    display_cols = {
        "id": "Run ID",
        "protein_pdb_id": "Protein",
        "compound_name": "Compound",
        "best_energy": "Energy (kcal/mol)",
        "exhaustiveness": "Exhaustiveness",
        "created_at": "Date",
    }
    available = [c for c in display_cols if c in df.columns]
    df_display = df[available].rename(columns=display_cols)

    # Format energy column
    if "Energy (kcal/mol)" in df_display.columns:
        df_display["Energy (kcal/mol)"] = df_display["Energy (kcal/mol)"].apply(
            lambda x: f"{x:.2f}" if x is not None else "N/A"
        )

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Run ID": st.column_config.NumberColumn(width="small"),
            "Energy (kcal/mol)": st.column_config.TextColumn(width="medium"),
            "Date": st.column_config.TextColumn(width="medium"),
        },
    )

    # -----------------------------------------------------------------------
    # Energy bar chart
    # -----------------------------------------------------------------------

    st.subheader("Binding Energy Overview")
    try:
        fig = energy_bar_chart(recent)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.error(f"Chart rendering failed: {exc}")

else:
    st.info(
        "No docking runs yet. Start by docking a compound on the **Dock** page!"
    )

st.divider()

# ---------------------------------------------------------------------------
# Quick action buttons
# ---------------------------------------------------------------------------

st.subheader("Quick Actions")

btn_col1, btn_col2, btn_col3 = st.columns(3)

if btn_col1.button("🔬 New Docking Job", use_container_width=True):
    st.switch_page("pages/dock.py")

if btn_col2.button("💊 ADMET Check", use_container_width=True):
    st.switch_page("pages/admet.py")

if btn_col3.button("📊 Browse Results", use_container_width=True):
    st.switch_page("pages/results.py")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "MoleCopilot -- Computational drug discovery toolkit for "
    "Professor Kaleem Mohammed's lab."
)
