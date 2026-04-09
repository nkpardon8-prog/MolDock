"""
MoleCopilot — Streamlit Entry Point

Main application file using st.navigation for multi-page routing.
Initializes the database and defines the page structure.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path so all pages can import core.* and components.*
sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(
    page_title="MoleCopilot",
    page_icon=":dna:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database on startup
from components.database import init_db

init_db()

# ---------------------------------------------------------------------------
# Define pages
# ---------------------------------------------------------------------------

dashboard = st.Page(
    "pages/dashboard.py",
    title="Dashboard",
    icon=":material/dashboard:",
    default=True,
)
dock_page = st.Page(
    "pages/dock.py",
    title="Dock",
    icon=":material/science:",
)
results = st.Page(
    "pages/results.py",
    title="Results",
    icon=":material/analytics:",
)
optimize = st.Page(
    "pages/optimize.py",
    title="Optimize",
    icon=":material/auto_fix_high:",
)
admet = st.Page(
    "pages/admet.py",
    title="ADMET",
    icon=":material/medication:",
)
viewer = st.Page(
    "pages/viewer_3d.py",
    title="3D Viewer",
    icon=":material/view_in_ar:",
)
lit = st.Page(
    "pages/literature_page.py",
    title="Literature",
    icon=":material/menu_book:",
)
chat = st.Page(
    "pages/chat.py",
    title="Chat",
    icon=":material/chat:",
)

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

pg = st.navigation(
    {
        "Overview": [dashboard],
        "Workflows": [dock_page, optimize, admet],
        "Analysis": [results, viewer, lit],
        "AI Assistant": [chat],
    }
)

# ---------------------------------------------------------------------------
# Sidebar branding
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("---")
    st.caption("MoleCopilot v2.0")
    st.caption("Molecular Docking Research Platform")

pg.run()
