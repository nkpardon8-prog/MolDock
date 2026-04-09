"""
MoleCopilot — Interactive 3D Protein-Ligand Viewer

Renders docked complexes from the database using py3Dmol via stmol.
Sidebar controls for surface, style, background, and H-bond display.
Fallback mode: enter a PDB ID to view just the protein.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.title("3D Protein-Ligand Viewer")
st.caption("Interactive visualization of docking results")

from stmol import showmol
from components.database import get_recent_docking_runs, get_docking_run
from components.mol3d import render_complex, render_protein
from core.utils import pdbqt_to_pdb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def _fetch_docking_runs(limit: int = 100) -> list[dict]:
    """Cached wrapper around DB query for docking runs."""
    return get_recent_docking_runs(limit=limit)


def _resolve_pdb_path(pdb_path: str | None, pdbqt_path: str | None) -> str | None:
    """Return a .pdb path, converting from .pdbqt if needed."""
    if pdb_path and Path(pdb_path).is_file():
        return pdb_path
    if pdbqt_path and Path(pdbqt_path).is_file():
        try:
            return pdbqt_to_pdb(pdbqt_path)
        except Exception as exc:
            st.warning(f"Could not convert PDBQT to PDB: {exc}")
            return None
    return None


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Viewer Settings")
    protein_style = st.selectbox(
        "Protein style",
        options=["cartoon", "stick", "sphere", "line"],
        index=0,
    )
    show_surface = st.checkbox("Show protein surface", value=False)
    show_hbonds = st.checkbox("Show hydrogen bonds", value=True)
    bg_color = st.color_picker("Background color", value="#0E1117")


# ---------------------------------------------------------------------------
# Main: select a docking run or fall back to PDB ID entry
# ---------------------------------------------------------------------------

runs = []
try:
    runs = _fetch_docking_runs()
except Exception as exc:
    st.error(f"Failed to load docking runs from database: {exc}")

if runs:
    # Build human-readable labels: "CompoundName vs PDB_ID (energy kcal/mol)"
    labels = []
    for r in runs:
        compound = r.get("compound_name") or r.get("compound_smiles", "Unknown")
        protein = r.get("protein_pdb_id", "???")
        energy = r.get("best_energy")
        energy_str = f" ({energy:.1f} kcal/mol)" if energy is not None else ""
        labels.append(f"{compound} vs {protein}{energy_str}")

    selected_idx = st.selectbox(
        "Select a docking run",
        options=range(len(labels)),
        format_func=lambda i: labels[i],
    )

    run_summary = runs[selected_idx]
    run_id = run_summary["id"]

    # Fetch full run details (includes file paths)
    run = None
    try:
        run = get_docking_run(run_id)
    except Exception as exc:
        st.error(f"Failed to load docking run details: {exc}")

    if run:
        # Resolve protein PDB path
        protein_pdb = _resolve_pdb_path(
            run.get("protein_pdb_path"),
            run.get("protein_pdbqt_path"),
        )

        # Resolve ligand PDB path — output_path from docking is usually .pdbqt
        ligand_pdb = None
        output_path = run.get("output_path")
        if output_path and Path(output_path).is_file():
            if output_path.endswith(".pdbqt"):
                try:
                    ligand_pdb = pdbqt_to_pdb(output_path)
                except Exception as exc:
                    st.warning(f"Could not convert docked ligand PDBQT: {exc}")
            elif output_path.endswith(".pdb") or output_path.endswith(".sdf"):
                ligand_pdb = output_path

        if protein_pdb:
            # Get interactions data if available
            interactions = run.get("interactions_json")
            if isinstance(interactions, str):
                import json
                try:
                    interactions = json.loads(interactions)
                except (json.JSONDecodeError, TypeError):
                    interactions = None

            try:
                view = render_complex(
                    protein_pdb=protein_pdb,
                    ligand_pdb=ligand_pdb,
                    interactions=interactions if show_hbonds else None,
                    show_surface=show_surface,
                    show_hbonds=show_hbonds,
                    style=protein_style,
                )
                # Apply background color
                view.setBackgroundColor(bg_color)
                showmol(view, height=600, width=800)
            except Exception as exc:
                st.error(f"3D rendering failed: {exc}")

            # ---------------------------------------------------------------
            # Run details below the viewer
            # ---------------------------------------------------------------
            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Best Energy",
                    f"{run.get('best_energy', 'N/A')} kcal/mol"
                    if run.get("best_energy") is not None
                    else "N/A",
                )
            with col2:
                st.metric("Exhaustiveness", run.get("exhaustiveness", "N/A"))
            with col3:
                compound_name = run.get("compound_name") or run.get("compound_smiles", "N/A")
                st.metric("Compound", compound_name)

            # All pose energies
            all_energies = run.get("all_energies_json")
            if isinstance(all_energies, str):
                import json as _json
                try:
                    all_energies = _json.loads(all_energies)
                except (ValueError, TypeError):
                    all_energies = None
            if all_energies and isinstance(all_energies, list):
                with st.expander("All pose energies"):
                    for i, e in enumerate(all_energies, 1):
                        st.text(f"  Pose {i}: {e:.2f} kcal/mol")

            # Interaction summary
            if interactions and isinstance(interactions, dict):
                with st.expander("Interaction Summary", expanded=True):
                    hbonds = interactions.get("hydrogen_bonds", [])
                    hydrophobic = interactions.get("hydrophobic_contacts", [])
                    salt_bridges = interactions.get("salt_bridges", [])
                    pi_stacking = interactions.get("pi_stacking", [])

                    icol1, icol2, icol3, icol4 = st.columns(4)
                    icol1.metric("H-bonds", len(hbonds))
                    icol2.metric("Hydrophobic", len(hydrophobic))
                    icol3.metric("Salt bridges", len(salt_bridges))
                    icol4.metric("Pi-stacking", len(pi_stacking))

                    if hbonds:
                        st.markdown("**Hydrogen Bonds:**")
                        for hb in hbonds:
                            donor = hb.get("donor_residue", hb.get("donor", "?"))
                            acceptor = hb.get("acceptor_residue", hb.get("acceptor", "?"))
                            dist = hb.get("distance", hb.get("dist_h_a"))
                            dist_str = f" ({dist:.2f} A)" if dist is not None else ""
                            st.text(f"  {donor} -- {acceptor}{dist_str}")

                    if hydrophobic:
                        st.markdown("**Hydrophobic Contacts:**")
                        for hp in hydrophobic:
                            residue = hp.get("residue", hp.get("resnr", "?"))
                            st.text(f"  {residue}")
        else:
            st.warning(
                "Protein PDB file not found on disk. "
                "The file may have been moved or deleted."
            )

else:
    # Fallback: no docking runs in DB — let user enter a PDB ID
    st.info(
        "No docking runs found in the database. "
        "Enter a PDB ID below to view just the protein structure."
    )

    pdb_id = st.text_input(
        "PDB ID",
        placeholder="e.g. 3S7S",
        max_chars=4,
    ).strip().upper()

    if pdb_id and len(pdb_id) == 4:
        # Check if we already have this protein's PDB file locally
        from core.utils import PROTEINS_DIR

        local_pdb = PROTEINS_DIR / f"{pdb_id}.pdb"

        if not local_pdb.is_file():
            with st.spinner(f"Fetching {pdb_id} from RCSB PDB..."):
                try:
                    from core.fetch_pdb import fetch_protein
                    result = fetch_protein(pdb_id)
                    fetched_path = result.get("pdb_path")
                    if fetched_path and Path(fetched_path).is_file():
                        local_pdb = Path(fetched_path)
                    else:
                        st.error(f"Could not download PDB file for {pdb_id}.")
                        local_pdb = None
                except Exception as exc:
                    st.error(f"Failed to fetch {pdb_id}: {exc}")
                    local_pdb = None

        if local_pdb and local_pdb.is_file():
            with st.sidebar:
                st.markdown("---")
                st.caption(f"Viewing: {pdb_id}")

            try:
                view = render_protein(
                    pdb_path=str(local_pdb),
                    style=protein_style,
                )
                if show_surface:
                    import py3Dmol
                    view.addSurface(
                        py3Dmol.VDW,
                        {"opacity": 0.5, "color": "white"},
                        {"model": 0},
                    )
                view.setBackgroundColor(bg_color)
                showmol(view, height=600, width=800)
            except Exception as exc:
                st.error(f"3D rendering failed: {exc}")
    elif pdb_id:
        st.warning("Please enter a valid 4-character PDB ID.")
