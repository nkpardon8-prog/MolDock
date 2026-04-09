"""
MoleCopilot Dock -- Docking job submission form with inline results.
"""

import sys
from pathlib import Path

# Add project root to path so core/ and components/ are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from components.database import (
    init_db,
    save_protein,
    save_compound,
    save_docking_run,
    get_protein_by_pdb_id,
)
from components.charts import energy_bar_chart, admet_radar

# Ensure DB tables exist
init_db()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="MoleCopilot -- Dock",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 Docking Job")
st.caption(
    "Fetch a protein, prepare a ligand, dock them, and view results -- "
    "all in one place."
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "dock_running": False,
    "dock_result": None,
    "dock_admet": None,
    "dock_protein_info": None,
    "dock_binding_site": None,
}
for key, val in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------------------------------------------------------------------------
# Input form
# ---------------------------------------------------------------------------

with st.form("docking_form"):
    st.subheader("Job Parameters")

    form_col1, form_col2 = st.columns(2)

    with form_col1:
        pdb_id = st.text_input(
            "PDB ID",
            value="",
            max_chars=4,
            placeholder="e.g. 3S7S",
            help="Four-character RCSB Protein Data Bank identifier.",
        )

        compound_input = st.text_input(
            "Compound (SMILES or name)",
            value="",
            placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O  or  aspirin",
            help=(
                "Enter a SMILES string or a compound name. Names will be "
                "resolved through PubChem."
            ),
        )

    with form_col2:
        exhaustiveness = st.slider(
            "Exhaustiveness",
            min_value=8,
            max_value=64,
            value=32,
            step=8,
            help=(
                "Thoroughness of the search. 8 = fast/rough, 32 = standard, "
                "64 = publication quality."
            ),
        )

        auto_detect_site = st.checkbox(
            "Auto-detect binding site",
            value=True,
            help=(
                "Automatically detect the binding site from co-crystallised "
                "ligands in the PDB file. Uncheck to manually specify coordinates."
            ),
        )

        if not auto_detect_site:
            manual_col1, manual_col2, manual_col3 = st.columns(3)
            center_x = manual_col1.number_input("Center X", value=0.0, format="%.2f")
            center_y = manual_col2.number_input("Center Y", value=0.0, format="%.2f")
            center_z = manual_col3.number_input("Center Z", value=0.0, format="%.2f")

            size_col1, size_col2, size_col3 = st.columns(3)
            size_x = size_col1.number_input("Size X", value=25.0, format="%.1f")
            size_y = size_col2.number_input("Size Y", value=25.0, format="%.1f")
            size_z = size_col3.number_input("Size Z", value=25.0, format="%.1f")

    submitted = st.form_submit_button(
        "🚀 Run Docking Pipeline",
        use_container_width=True,
        type="primary",
    )

# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

if submitted:
    # Validate inputs
    if not pdb_id or len(pdb_id.strip()) != 4:
        st.error("Please enter a valid 4-character PDB ID.")
        st.stop()
    if not compound_input.strip():
        st.error("Please enter a compound SMILES or name.")
        st.stop()

    pdb_id = pdb_id.strip().upper()
    compound_input = compound_input.strip()

    with st.status("Running docking pipeline...", expanded=True) as status:
        # ==================================================================
        # Step 1: Fetch protein
        # ==================================================================
        st.write("**Step 1/7:** Fetching protein from RCSB...")
        try:
            from core.fetch_pdb import fetch_protein, get_protein_info

            fetch_result = fetch_protein(pdb_id)
            pdb_path = fetch_result["file_path"]
            st.write(f"  Downloaded: `{Path(pdb_path).name}`")

            # Get protein metadata
            try:
                protein_info = get_protein_info(pdb_id)
                st.session_state.dock_protein_info = protein_info
                st.write(f"  Title: {protein_info.get('title', 'N/A')}")
            except Exception:
                protein_info = {}

        except Exception as exc:
            st.error(f"Failed to fetch protein {pdb_id}: {exc}")
            status.update(label="Pipeline failed at Step 1", state="error")
            st.stop()

        # ==================================================================
        # Step 2: Detect binding site (on ORIGINAL PDB, before prep)
        # ==================================================================
        st.write("**Step 2/7:** Detecting binding site...")
        try:
            from core.prep_protein import detect_binding_site

            if auto_detect_site:
                binding_site = detect_binding_site(pdb_path)
            else:
                binding_site = {
                    "center_x": center_x,
                    "center_y": center_y,
                    "center_z": center_z,
                    "size_x": size_x,
                    "size_y": size_y,
                    "size_z": size_z,
                    "ligand_found": False,
                    "ligand_resname": "",
                    "residues_nearby": [],
                }
            st.session_state.dock_binding_site = binding_site

            if binding_site.get("ligand_found"):
                st.write(
                    f"  Found co-crystallised ligand: "
                    f"**{binding_site['ligand_resname']}** -- "
                    f"centre ({binding_site['center_x']:.1f}, "
                    f"{binding_site['center_y']:.1f}, "
                    f"{binding_site['center_z']:.1f})"
                )
            else:
                st.write(
                    "  No co-crystallised ligand found. Using protein centre of mass."
                )
        except Exception as exc:
            st.error(f"Binding site detection failed: {exc}")
            status.update(label="Pipeline failed at Step 2", state="error")
            st.stop()

        # ==================================================================
        # Step 3: Prepare protein
        # ==================================================================
        st.write("**Step 3/7:** Preparing protein (clean, add H, convert to PDBQT)...")
        try:
            from core.prep_protein import prepare_protein

            prep_result = prepare_protein(pdb_path)
            protein_pdbqt = prep_result["pdbqt_path"]
            clean_pdb = prep_result["clean_pdb"]
            st.write(f"  PDBQT: `{Path(protein_pdbqt).name}`")
        except Exception as exc:
            st.error(f"Protein preparation failed: {exc}")
            status.update(label="Pipeline failed at Step 3", state="error")
            st.stop()

        # ==================================================================
        # Step 4: Resolve compound input
        # ==================================================================
        st.write("**Step 4/7:** Resolving compound...")

        smiles = None
        compound_name = compound_input

        try:
            from core.utils import validate_smiles

            if validate_smiles(compound_input):
                # Input is a SMILES string
                smiles = compound_input
                compound_name = compound_input[:40]
                st.write(f"  Input recognised as SMILES: `{smiles[:60]}`")
            else:
                # Input is a compound name -- search PubChem
                st.write(f"  Searching PubChem for '{compound_input}'...")
                from core.fetch_compounds import search_pubchem

                results = search_pubchem(compound_input, max_results=1)
                if not results:
                    st.error(
                        f"No compounds found on PubChem for '{compound_input}'. "
                        "Try entering a SMILES string instead."
                    )
                    status.update(label="Pipeline failed at Step 4", state="error")
                    st.stop()

                hit = results[0]
                smiles = hit.get("smiles", "")
                compound_name = hit.get("iupac_name") or compound_input

                if not smiles:
                    st.error(
                        f"PubChem returned no SMILES for '{compound_input}' "
                        f"(CID {hit.get('cid')}). Try entering the SMILES directly."
                    )
                    status.update(label="Pipeline failed at Step 4", state="error")
                    st.stop()

                st.write(
                    f"  Found: **{compound_input}** (CID {hit['cid']}) -- "
                    f"SMILES: `{smiles[:60]}`"
                )
        except Exception as exc:
            st.error(f"Compound resolution failed: {exc}")
            status.update(label="Pipeline failed at Step 4", state="error")
            st.stop()

        # ==================================================================
        # Step 5: Prepare ligand (SMILES -> SDF -> PDBQT)
        # ==================================================================
        st.write("**Step 5/7:** Preparing ligand (3D coords, PDBQT)...")
        try:
            from core.fetch_compounds import smiles_to_sdf
            from core.prep_ligand import prepare_ligand

            # Generate SDF
            sdf_result = smiles_to_sdf(smiles, compound_name)
            sdf_path = sdf_result["sdf_path"]

            # Convert to PDBQT
            lig_result = prepare_ligand(sdf_path)
            ligand_pdbqt = lig_result["pdbqt_path"]
            st.write(f"  PDBQT: `{Path(ligand_pdbqt).name}` (method: {lig_result['method']})")
        except Exception as exc:
            st.error(f"Ligand preparation failed: {exc}")
            status.update(label="Pipeline failed at Step 5", state="error")
            st.stop()

        # ==================================================================
        # Step 6: Dock with AutoDock Vina
        # ==================================================================
        st.write("**Step 6/7:** Running AutoDock Vina... (this may take a few minutes)")
        try:
            from core.dock_vina import dock

            center = (
                binding_site["center_x"],
                binding_site["center_y"],
                binding_site["center_z"],
            )
            box_size = (
                binding_site["size_x"],
                binding_site["size_y"],
                binding_site["size_z"],
            )

            dock_result = dock(
                protein_pdbqt=protein_pdbqt,
                ligand_pdbqt=ligand_pdbqt,
                center=center,
                box_size=box_size,
                exhaustiveness=exhaustiveness,
            )
            st.session_state.dock_result = dock_result
            st.write(
                f"  Best energy: **{dock_result['best_energy']:.2f} kcal/mol** "
                f"({dock_result['n_poses']} poses)"
            )
        except Exception as exc:
            st.error(f"Docking failed: {exc}")
            status.update(label="Pipeline failed at Step 6", state="error")
            st.stop()

        # ==================================================================
        # Step 7: ADMET quick check
        # ==================================================================
        st.write("**Step 7/7:** Running ADMET / drug-likeness check...")
        try:
            from core.admet_check import full_admet

            admet_result = full_admet(smiles)
            st.session_state.dock_admet = admet_result
            st.write(
                f"  Assessment: **{admet_result['assessment']}** "
                f"(score: {admet_result['drug_likeness_score']:.2f})"
            )
        except Exception as exc:
            st.warning(f"ADMET check failed (non-fatal): {exc}")
            admet_result = None

        # ==================================================================
        # Save everything to database
        # ==================================================================
        st.write("Saving results to database...")
        try:
            protein_id = save_protein(
                pdb_id=pdb_id,
                title=protein_info.get("title"),
                organism=protein_info.get("organism"),
                resolution=protein_info.get("resolution"),
                method=protein_info.get("method"),
                pdb_path=pdb_path,
                pdbqt_path=protein_pdbqt,
                binding_site=binding_site,
            )

            compound_id = save_compound(
                name=compound_name,
                smiles=smiles,
                sdf_path=sdf_path,
                pdbqt_path=ligand_pdbqt,
                admet_data=admet_result,
            )

            run_id = save_docking_run(
                protein_id=protein_id,
                compound_id=compound_id,
                best_energy=dock_result["best_energy"],
                all_energies=dock_result["all_energies"],
                exhaustiveness=exhaustiveness,
                center=center,
                size=box_size,
                output_path=dock_result["output_path"],
            )
            st.write(f"  Saved as docking run **#{run_id}**")
        except Exception as exc:
            st.warning(f"Database save failed (non-fatal): {exc}")

        status.update(label="Pipeline complete!", state="complete")

# ---------------------------------------------------------------------------
# Display results (persisted in session_state)
# ---------------------------------------------------------------------------

dock_result = st.session_state.dock_result
admet_result = st.session_state.dock_admet

if dock_result is not None:
    st.divider()
    st.subheader("Docking Results")

    # Summary metrics
    res_col1, res_col2, res_col3, res_col4, res_col5 = st.columns(5)

    res_col1.metric(
        "Best Energy",
        f"{dock_result['best_energy']:.2f} kcal/mol",
        help="Most negative = strongest binding",
    )
    res_col2.metric(
        "Poses Found",
        dock_result["n_poses"],
    )

    energy_quality = dock_result["best_energy"]
    if energy_quality < -9.0:
        quality_label = "Excellent"
    elif energy_quality < -8.0:
        quality_label = "Strong"
    elif energy_quality < -7.0:
        quality_label = "Moderate"
    else:
        quality_label = "Weak"
    res_col3.metric("Binding Quality", quality_label)

    if admet_result and admet_result.get("valid"):
        res_col4.metric(
            "Drug-likeness",
            admet_result["assessment"],
            help=f"Score: {admet_result['drug_likeness_score']:.2f}",
        )
        sa_score = admet_result.get("sa_score", "N/A")
        sa_label = admet_result.get("synthetic_assessment", "N/A")
        res_col5.metric(
            "SA Score",
            f"{sa_score:.1f}" if isinstance(sa_score, (int, float)) else sa_score,
            delta=sa_label,
            delta_color="off",
        )
    else:
        res_col4.metric("Drug-likeness", "N/A")
        res_col5.metric("SA Score", "N/A")

    # All pose energies
    if dock_result.get("all_energies"):
        with st.expander("All Pose Energies", expanded=False):
            import pandas as pd

            pose_data = [
                {"Pose": i + 1, "Energy (kcal/mol)": f"{e:.2f}"}
                for i, e in enumerate(dock_result["all_energies"])
            ]
            st.dataframe(
                pd.DataFrame(pose_data),
                use_container_width=True,
                hide_index=True,
            )

    # ADMET details
    if admet_result and admet_result.get("valid"):
        st.subheader("ADMET / Drug-Likeness Profile")

        admet_col1, admet_col2 = st.columns([1, 1])

        with admet_col1:
            st.markdown("**Lipinski Rule of Five**")
            lip = admet_result["lipinski"]
            lip_data = {
                "Property": ["MW", "LogP", "HBD", "HBA"],
                "Value": [lip["mw"], lip["logp"], lip["hbd"], lip["hba"]],
                "Threshold": ["<= 500", "<= 5", "<= 5", "<= 10"],
                "Pass": [
                    "Pass" if lip["mw"] <= 500 else "FAIL",
                    "Pass" if lip["logp"] <= 5 else "FAIL",
                    "Pass" if lip["hbd"] <= 5 else "FAIL",
                    "Pass" if lip["hba"] <= 10 else "FAIL",
                ],
            }
            import pandas as pd

            st.dataframe(
                pd.DataFrame(lip_data),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("**Veber Rules**")
            veb = admet_result["veber"]
            veb_data = {
                "Property": ["Rotatable Bonds", "TPSA"],
                "Value": [veb["rotatable_bonds"], veb["tpsa"]],
                "Threshold": ["<= 10", "<= 140"],
                "Pass": [
                    "Pass" if veb["rotatable_bonds"] <= 10 else "FAIL",
                    "Pass" if veb["tpsa"] <= 140 else "FAIL",
                ],
            }
            st.dataframe(
                pd.DataFrame(veb_data),
                use_container_width=True,
                hide_index=True,
            )

        with admet_col2:
            try:
                fig = admet_radar(admet_result, compound_name="Compound")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as exc:
                st.error(f"Radar chart failed: {exc}")

    # Output file paths
    with st.expander("Output File Paths", expanded=False):
        st.code(f"Docked PDBQT: {dock_result.get('output_path', 'N/A')}")
        st.code(f"Receptor:     {dock_result.get('receptor', 'N/A')}")
        st.code(f"Ligand:       {dock_result.get('ligand', 'N/A')}")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "MoleCopilot -- Dock. Pipeline: fetch protein -> detect site -> "
    "prep protein -> resolve compound -> prep ligand -> dock -> ADMET."
)
