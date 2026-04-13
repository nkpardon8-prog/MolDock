#!/usr/bin/env python3
"""MoleCopilot MCP Server — Molecular Docking Research Agent.

Exposes 26 tools for computational drug discovery via the Model Context Protocol.
Uses FastMCP for automatic schema generation from type hints.
All heavy imports are lazy (inside tool functions) for fast startup.
Every tool that produces artifacts saves to SQLite for dashboard persistence.
"""
import sys
import json
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("molecopilot")


# ── DB persistence helpers ─────────────────────────────────────────────────

from components.database import (
    init_db,
    save_protein,
    save_compound,
    save_docking_run,
    get_protein_by_pdb_id,
    get_compound_by_smiles,
)

try:
    init_db()
except Exception as e:
    print(f"[MoleCopilot] DB init warning (non-fatal): {e}", file=sys.stderr)


def _db_save(func, *args, **kwargs):
    """Best-effort DB save — never breaks the pipeline."""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"[MoleCopilot] DB save warning: {e}", file=sys.stderr)
        return None


def _extract_pdb_id(pdbqt_path: str) -> str:
    """Extract PDB ID from a filename like '3S7S_clean.pdbqt' → '3S7S'.
    Returns the stem prefix only if it looks like a 4-char PDB ID."""
    stem = Path(pdbqt_path).stem.split("_")[0].upper()
    if len(stem) == 4 and stem.isalnum():
        return stem
    return stem  # best effort


# ============================================================
# CORE PIPELINE (6 tools)
# ============================================================

@mcp.tool()
def fetch_protein(pdb_id: str) -> dict:
    """Download a protein structure from RCSB PDB by its 4-character ID (e.g., '3S7S', '3H82').
    Returns the local file path and basic protein metadata."""
    from core.fetch_pdb import fetch_protein as _fetch, get_protein_info
    result = _fetch(pdb_id)
    info = {}
    try:
        info = get_protein_info(pdb_id)
        result["info"] = info
    except Exception:
        pass

    # Persist to DB
    _db_save(save_protein,
             pdb_id=pdb_id,
             title=info.get("title"),
             organism=info.get("organism"),
             resolution=info.get("resolution"),
             method=info.get("method"),
             pdb_path=result.get("file_path"))
    return result


@mcp.tool()
def prepare_protein(pdb_path: str) -> dict:
    """Clean a protein structure for docking: remove water, add hydrogens,
    fix missing atoms, convert to PDBQT. Also detects the binding site
    from the ORIGINAL PDB before cleaning removes co-crystallized ligands."""
    from core.prep_protein import prepare_protein as _prep, detect_binding_site as _detect
    site = _detect(pdb_path)
    result = _prep(pdb_path)
    result["binding_site"] = site

    # Persist: update protein with pdbqt_path + binding site (merges with existing)
    pdb_id = _extract_pdb_id(pdb_path)
    _db_save(save_protein,
             pdb_id=pdb_id,
             pdbqt_path=result.get("pdbqt_path"),
             binding_site=site)
    return result


@mcp.tool()
def fetch_compound(cid: int = None, smiles: str = None, name: str = None) -> dict:
    """Get a compound by PubChem CID or SMILES string. Downloads/generates 3D SDF structure."""
    from core.fetch_compounds import fetch_compound_sdf, smiles_to_sdf
    if cid:
        result = fetch_compound_sdf(cid)
        # fetch_compound_sdf doesn't return SMILES — try to get it from PubChem
        compound_smiles = smiles
        if not compound_smiles:
            try:
                from core.fetch_compounds import search_pubchem
                hits = search_pubchem(str(cid), max_results=1)
                if hits:
                    compound_smiles = hits[0].get("smiles")
            except Exception:
                pass
        _db_save(save_compound,
                 name=name,
                 smiles=compound_smiles,
                 cid=cid,
                 sdf_path=result.get("sdf_path"))
        return result
    elif smiles:
        result = smiles_to_sdf(smiles, name or "compound")
        _db_save(save_compound,
                 name=name,
                 smiles=smiles,
                 sdf_path=result.get("sdf_path"))
        return result
    raise ValueError("Provide either cid or smiles")


@mcp.tool()
def prepare_ligand(input_path: str = None, smiles: str = None, name: str = None) -> dict:
    """Prepare a ligand for docking — converts SDF/MOL2/PDB/SMILES to PDBQT format
    using Meeko (primary) or Open Babel (fallback)."""
    from core.prep_ligand import prepare_ligand as _prep
    if smiles and not input_path:
        from core.fetch_compounds import smiles_to_sdf
        sdf_result = smiles_to_sdf(smiles, name or "compound")
        input_path = sdf_result["sdf_path"]
    result = _prep(input_path)

    # Update compound with pdbqt_path if we know the SMILES
    if smiles:
        _db_save(save_compound,
                 name=name,
                 smiles=smiles,
                 pdbqt_path=result.get("pdbqt_path"))
    return result


@mcp.tool()
def dock(protein_pdbqt: str, ligand_pdbqt: str,
         center_x: float, center_y: float, center_z: float,
         size_x: float = 25, size_y: float = 25, size_z: float = 25,
         exhaustiveness: int = 32) -> dict:
    """Run molecular docking with AutoDock Vina. Provide receptor PDBQT, ligand PDBQT,
    and search box center coordinates (REQUIRED — get from detect_binding_site or prepare_protein).
    Box size defaults to 25x25x25 Angstroms. Exhaustiveness: 8=fast, 32=standard, 64=publication."""
    from core.dock_vina import dock as _dock
    result = _dock(protein_pdbqt, ligand_pdbqt,
                   center=(center_x, center_y, center_z),
                   box_size=(size_x, size_y, size_z),
                   exhaustiveness=exhaustiveness)

    # Persist: look up or create protein/compound, then save docking run
    pdb_id = _extract_pdb_id(protein_pdbqt)
    protein = get_protein_by_pdb_id(pdb_id) if pdb_id else None
    protein_id = protein["id"] if protein else _db_save(
        save_protein, pdb_id=pdb_id, pdbqt_path=protein_pdbqt)

    compound_id = _db_save(save_compound, pdbqt_path=ligand_pdbqt)

    if protein_id and compound_id:
        _db_save(save_docking_run,
                 protein_id=protein_id,
                 compound_id=compound_id,
                 best_energy=result.get("best_energy"),
                 all_energies=result.get("all_energies"),
                 exhaustiveness=exhaustiveness,
                 center=(center_x, center_y, center_z),
                 size=(size_x, size_y, size_z),
                 output_path=result.get("output_path"))
    return result


@mcp.tool()
def full_pipeline(protein_pdb_id: str, compound_query: str = None,
                  smiles: str = None, compound_name: str = None,
                  exhaustiveness: int = 32) -> dict:
    """Run the COMPLETE docking pipeline end-to-end. Provide a PDB ID and either
    a compound name or SMILES string. Fetches, preps, docks, analyzes, and reports.
    WARNING: This may take several minutes for exhaustiveness >= 32."""
    from core.fetch_pdb import fetch_protein as _fetch_prot, get_protein_info
    from core.prep_protein import prepare_protein as _prep_prot, detect_binding_site as _detect
    from core.fetch_compounds import search_pubchem, smiles_to_sdf
    from core.prep_ligand import prepare_ligand as _prep_lig
    from core.dock_vina import dock as _dock
    from core.admet_check import full_admet
    from core.analyze_results import generate_summary

    # 1. Fetch & prep protein
    prot = _fetch_prot(protein_pdb_id)
    site = _detect(prot["file_path"])
    prepped = _prep_prot(prot["file_path"])
    center = (site["center_x"], site["center_y"], site["center_z"])
    box = (site["size_x"], site["size_y"], site["size_z"])

    # Get protein metadata for DB
    prot_info = {}
    try:
        prot_info = get_protein_info(protein_pdb_id)
    except Exception:
        pass

    # 2. Get & prep ligand
    if smiles:
        sdf = smiles_to_sdf(smiles, compound_name or "compound")
    elif compound_query:
        results = search_pubchem(compound_query, max_results=1)
        if not results:
            return {"error": f"No compounds found for '{compound_query}'",
                    "message": f"PubChem search returned no results for '{compound_query}'"}
        from core.fetch_compounds import fetch_compound_sdf
        sdf = fetch_compound_sdf(results[0]["cid"])
        smiles = results[0].get("smiles")
        compound_name = compound_name or results[0].get("name", compound_query)
    else:
        raise ValueError("Provide either compound_query or smiles")
    lig = _prep_lig(sdf["sdf_path"])

    # 3. Dock
    dock_result = _dock(prepped["pdbqt_path"], lig["pdbqt_path"],
                        center=center, box_size=box, exhaustiveness=exhaustiveness)

    # 4. Interaction analysis
    interactions = None
    try:
        from core.analyze_results import get_interactions
        interactions = get_interactions(prepped["clean_pdb"], dock_result["output_path"])
    except Exception as e:
        print(f"[MoleCopilot] Interaction analysis failed: {e}", file=sys.stderr)

    # 5. ADMET
    admet = full_admet(smiles) if smiles else None

    # 6. Summary
    project = compound_name or compound_query or "pipeline_run"
    summary = generate_summary(
        docking_results=[{**dock_result, "name": project}],
        admet_results=[{**admet, "name": project}] if admet else None,
        interactions=[{**interactions, "compound_name": project}] if interactions else None,
        project_name=project
    )

    # ── Persist everything to DB ───────────────────────────────────────
    protein_id = _db_save(save_protein,
                          pdb_id=protein_pdb_id,
                          title=prot_info.get("title"),
                          organism=prot_info.get("organism"),
                          resolution=prot_info.get("resolution"),
                          method=prot_info.get("method"),
                          pdb_path=prot["file_path"],
                          pdbqt_path=prepped["pdbqt_path"],
                          binding_site=site)

    compound_id = _db_save(save_compound,
                           name=compound_name or compound_query,
                           smiles=smiles,
                           sdf_path=sdf.get("sdf_path"),
                           pdbqt_path=lig.get("pdbqt_path"),
                           admet_data=admet)

    if protein_id and compound_id:
        _db_save(save_docking_run,
                 protein_id=protein_id,
                 compound_id=compound_id,
                 best_energy=dock_result["best_energy"],
                 all_energies=dock_result.get("all_energies"),
                 exhaustiveness=exhaustiveness,
                 center=center,
                 size=box,
                 output_path=dock_result.get("output_path"),
                 interactions=interactions)

    return {
        "best_energy": dock_result["best_energy"],
        "compound": compound_name or compound_query,
        "protein": protein_pdb_id,
        "admet": admet,
        "interactions": interactions,
        "report_path": summary["report_path"],
        "summary": summary["markdown"],
        "message": f"Docking complete: {project} vs {protein_pdb_id} = {dock_result['best_energy']} kcal/mol"
    }


# ============================================================
# BATCH OPERATIONS (3 tools)
# ============================================================

@mcp.tool()
def batch_prepare_ligands(input_dir: str) -> dict:
    """Prepare all ligand files (.sdf, .mol2, .pdb) in a directory for docking.
    Returns list of prepared PDBQT paths and any failures."""
    from core.prep_ligand import batch_prepare
    return batch_prepare(input_dir)


@mcp.tool()
def batch_dock(protein_pdbqt: str, ligand_dir: str,
               center_x: float, center_y: float, center_z: float,
               size_x: float = 25, size_y: float = 25, size_z: float = 25,
               exhaustiveness: int = 32) -> dict:
    """Dock all PDBQT ligands in a directory against a protein target.
    Center coordinates are REQUIRED (get from detect_binding_site).
    Returns ranked results CSV path and top hits."""
    from core.dock_vina import batch_dock as _batch
    result = _batch(protein_pdbqt, ligand_dir,
                    center=(center_x, center_y, center_z),
                    box_size=(size_x, size_y, size_z),
                    exhaustiveness=exhaustiveness)

    # Persist each successful hit to DB
    pdb_id = _extract_pdb_id(protein_pdbqt)
    protein = get_protein_by_pdb_id(pdb_id) if pdb_id else None
    protein_id = protein["id"] if protein else _db_save(
        save_protein, pdb_id=pdb_id, pdbqt_path=protein_pdbqt)

    if protein_id:
        lig_dir = Path(ligand_dir).resolve()
        for hit in result.get("top_hits", []):
            ligand_filename = hit.get("ligand", "")
            ligand_name = Path(ligand_filename).stem if ligand_filename else None
            full_path = str(lig_dir / ligand_filename) if ligand_filename else None
            compound_id = _db_save(save_compound,
                                   name=ligand_name,
                                   pdbqt_path=full_path)
            if compound_id:
                _db_save(save_docking_run,
                         protein_id=protein_id,
                         compound_id=compound_id,
                         best_energy=hit.get("best_energy"),
                         exhaustiveness=exhaustiveness,
                         center=(center_x, center_y, center_z),
                         size=(size_x, size_y, size_z))
    return result


@mcp.tool()
def batch_admet(smiles_list: list, names: list = None) -> dict:
    """Run ADMET/drug-likeness analysis on multiple compounds.
    Provide a list of SMILES strings and optional compound names."""
    from core.admet_check import batch_admet as _batch
    result = _batch(smiles_list, names)

    # Persist each compound with ADMET data
    for i, admet_result in enumerate(result.get("results", [])):
        nm = names[i] if names and i < len(names) else None
        smi = smiles_list[i] if i < len(smiles_list) else None
        _db_save(save_compound, name=nm, smiles=smi, admet_data=admet_result)
    return result


# ============================================================
# ANALYSIS (5 tools)
# ============================================================

@mcp.tool()
def detect_binding_site(pdb_path: str, ligand_resname: str = None) -> dict:
    """Detect the binding site on a protein from co-crystallized ligand position.
    Must be called on the ORIGINAL PDB (before protein preparation removes ligands)."""
    from core.prep_protein import detect_binding_site as _detect
    return _detect(pdb_path, ligand_resname)


@mcp.tool()
def analyze_interactions(protein_pdb: str, ligand_path: str) -> dict:
    """Analyze protein-ligand interactions (H-bonds, hydrophobic, pi-stacking, etc.)
    using PLIP. Provide protein PDB and ligand PDB or PDBQT (auto-converts if needed)."""
    from core.analyze_results import get_interactions
    return get_interactions(protein_pdb, ligand_path)


@mcp.tool()
def rank_results(results_dir: str) -> dict:
    """Rank all docked compounds in a results directory by binding energy.
    Returns sorted rankings with energies and file paths."""
    from core.analyze_results import rank_results as _rank
    return _rank(results_dir)


@mcp.tool()
def admet_check(smiles: str) -> dict:
    """Run comprehensive drug-likeness analysis on a compound (SMILES string).
    Checks Lipinski Rule of 5, Veber rules, and additional descriptors.
    Returns drug-likeness score (0-1) and detailed property breakdown."""
    from core.admet_check import full_admet
    result = full_admet(smiles)

    # Persist compound with ADMET data
    _db_save(save_compound, smiles=smiles, admet_data=result)
    return result


@mcp.tool()
def compare_compounds(smiles_list: list, names: list = None,
                      protein_pdbqt: str = None,
                      center_x: float = 0, center_y: float = 0, center_z: float = 0,
                      size_x: float = 25, size_y: float = 25, size_z: float = 25) -> dict:
    """Compare multiple compounds: ADMET profiles side-by-side, optional docking.
    Provide SMILES list and optionally a protein target for docking comparison."""
    from core.admet_check import batch_admet as _batch_admet
    result = _batch_admet(smiles_list, names)

    # Persist ADMET results
    for i, admet_result in enumerate(result.get("results", [])):
        nm = names[i] if names and i < len(names) else None
        smi = smiles_list[i] if i < len(smiles_list) else None
        _db_save(save_compound, name=nm, smiles=smi, admet_data=admet_result)

    if protein_pdbqt and (center_x != 0 or center_y != 0 or center_z != 0):
        from core.fetch_compounds import smiles_to_sdf
        from core.prep_ligand import prepare_ligand as _prep
        from core.dock_vina import dock as _dock

        pdb_id = _extract_pdb_id(protein_pdbqt)
        protein = get_protein_by_pdb_id(pdb_id) if pdb_id else None
        protein_id = protein["id"] if protein else _db_save(
            save_protein, pdb_id=pdb_id, pdbqt_path=protein_pdbqt)

        docking = []
        for i, smi in enumerate(smiles_list):
            nm = names[i] if names and i < len(names) else f"compound_{i}"
            try:
                sdf = smiles_to_sdf(smi, nm)
                lig = _prep(sdf["sdf_path"])
                d = _dock(protein_pdbqt, lig["pdbqt_path"],
                          center=(center_x, center_y, center_z),
                          box_size=(size_x, size_y, size_z), exhaustiveness=8)
                docking.append({"name": nm, "energy": d["best_energy"]})

                # Persist docking run
                if protein_id:
                    compound_id = _db_save(save_compound,
                                           name=nm, smiles=smi,
                                           sdf_path=sdf.get("sdf_path"),
                                           pdbqt_path=lig.get("pdbqt_path"))
                    if compound_id:
                        _db_save(save_docking_run,
                                 protein_id=protein_id,
                                 compound_id=compound_id,
                                 best_energy=d["best_energy"],
                                 all_energies=d.get("all_energies"),
                                 exhaustiveness=8,
                                 center=(center_x, center_y, center_z),
                                 size=(size_x, size_y, size_z),
                                 output_path=d.get("output_path"))
            except Exception as e:
                docking.append({"name": nm, "energy": None, "error": str(e)})
        result["docking"] = docking
    return result


# ============================================================
# GENERATIVE CHEMISTRY (3 tools)
# ============================================================

@mcp.tool()
def generate_analogs(smiles: str, num_molecules: int = 10,
                     scaled_radius: float = 0.5) -> dict:
    """Generate structural analogs of a compound using NVIDIA MolMIM AI.
    Provide a SMILES string. Returns novel molecules similar to the input.
    scaled_radius controls diversity: 0=very similar, 2=very different."""
    from core.bionemo import sample_analogs
    result = sample_analogs(smiles, num_molecules, scaled_radius)
    for i, analog in enumerate(result.get("analogs", [])):
        _db_save(save_compound,
                 name=f"analog_{i+1}_of_{smiles[:20]}",
                 smiles=analog.get("smiles"))
    return result


@mcp.tool()
def optimize_compound(smiles: str, property_name: str = "QED",
                      num_molecules: int = 20,
                      min_similarity: float = 0.3) -> dict:
    """Optimize a compound for drug-like properties using NVIDIA MolMIM AI with CMA-ES.
    Properties: 'QED' (drug-likeness) or 'plogP' (penalized LogP).
    Returns optimized analogs ranked by the target property score."""
    from core.bionemo import optimize_molecules
    result = optimize_molecules(smiles, property_name, num_molecules, min_similarity)
    for i, analog in enumerate(result.get("analogs", [])):
        _db_save(save_compound,
                 name=f"optimized_{i+1}_of_{smiles[:20]}",
                 smiles=analog.get("smiles"))
    return result


@mcp.tool()
def synthetic_check(smiles: str) -> dict:
    """Check synthetic accessibility of a compound. Returns SA score (1-10)
    where 1=easy to synthesize and 10=very difficult. Also returns assessment
    category: Easy/Moderate/Difficult/Very Difficult."""
    from core.admet_check import calculate_sa_score
    return calculate_sa_score(smiles)


# ============================================================
# DATABASE QUERIES (5 tools)
# ============================================================

@mcp.tool()
def search_proteins(query: str, max_results: int = 10) -> dict:
    """Search RCSB PDB for protein structures by name, function, or keyword.
    Example: 'human aromatase', 'HIF-2alpha', 'BACE1 inhibitor complex'."""
    from core.fetch_pdb import search_pdb
    return {"results": search_pdb(query, max_results)}


@mcp.tool()
def search_compounds(query: str, max_results: int = 20) -> dict:
    """Search PubChem for compounds by name. Returns CID, SMILES, MW, formula.
    Example: 'aspirin', 'thymoquinone', 'exemestane'."""
    from core.fetch_compounds import search_pubchem
    return {"compounds": search_pubchem(query, max_results)}


@mcp.tool()
def search_natural_products(query: str, search_type: str = "name", max_results: int = 20) -> dict:
    """Search the Natural Products Atlas database for natural product compounds.
    search_type can be 'name' (text search) or 'similarity' (SMILES-based Tanimoto search)."""
    from core.fetch_compounds import search_npatlas, search_npatlas_similar
    if search_type == "similarity":
        results = search_npatlas_similar(query, max_results=max_results)
    else:
        results = search_npatlas(query, max_results=max_results)
    return {"results": results, "count": len(results), "search_type": search_type}


@mcp.tool()
def search_literature(query: str, max_results: int = 10) -> dict:
    """Search PubMed for scientific publications. Returns titles, abstracts, DOIs.
    Example: 'aromatase inhibitor molecular docking', 'HIF-2α marine natural product'."""
    from core.literature import search_pubmed
    return {"publications": search_pubmed(query, max_results)}


@mcp.tool()
def get_known_actives(target_name: str = None, uniprot_id: str = None) -> dict:
    """Query ChEMBL for known bioactive compounds against a protein target.
    Returns compounds with IC50/Ki/EC50 values. Provide target name or UniProt ID.
    Example: target_name='aromatase' or uniprot_id='P11511'."""
    from core.literature import get_known_actives as _get
    return _get(target_name=target_name, uniprot_id=uniprot_id)


# ============================================================
# VISUALIZATION & OUTPUT (4 tools)
# ============================================================

@mcp.tool()
def draw_molecule(smiles: str, name: str = None) -> dict:
    """Generate a 2D chemical structure depiction from a SMILES string.
    Returns path to the saved PNG image."""
    from core.generate_figures import draw_molecule_2d
    path = draw_molecule_2d(smiles, name)
    return {"image_path": path, "smiles": smiles, "name": name or "molecule",
            "message": f"2D structure saved to {path}"}


@mcp.tool()
def protein_info(pdb_id: str = None, uniprot_id: str = None, protein_name: str = None) -> dict:
    """Get detailed protein information from RCSB PDB and/or UniProt.
    Returns annotations, domains, organism, known structures, disease associations,
    and ChEMBL target summary (bioactivity statistics) when a UniProt accession is available."""
    result = {}
    if pdb_id:
        from core.fetch_pdb import get_protein_info
        result["pdb"] = get_protein_info(pdb_id)
    if uniprot_id or protein_name:
        from core.literature import get_uniprot_info
        result["uniprot"] = get_uniprot_info(uniprot_id, protein_name)
    if not result:
        raise ValueError("Provide pdb_id, uniprot_id, or protein_name")

    # Best-effort ChEMBL target summary when a UniProt accession is known
    resolved_uniprot = uniprot_id
    if not resolved_uniprot and result.get("pdb"):
        resolved_uniprot = result["pdb"].get("uniprot_accession")
    if resolved_uniprot:
        try:
            from core.literature import get_target_summary
            summary = get_target_summary(resolved_uniprot)
            if summary:
                result["target_summary"] = summary
        except Exception:
            pass

    return result


@mcp.tool()
def generate_report(project_name: str, results_dir: str = None) -> dict:
    """Generate a comprehensive markdown summary report for a docking project.
    Combines docking scores, ADMET profiles, and interaction analysis.
    Also generates figures (binding energy bar chart, energy distribution) if data exists."""
    from core.analyze_results import rank_results as _rank, generate_summary
    rankings = _rank(results_dir) if results_dir else {"rankings": []}
    ranked = rankings.get("rankings", [])
    figures = []
    if len(ranked) > 1:
        from core.generate_figures import plot_binding_energies, plot_energy_distribution
        try:
            fig1 = plot_binding_energies(ranked)
            if fig1:
                figures.append(fig1)
        except Exception:
            pass
        try:
            fig2 = plot_energy_distribution(ranked)
            if fig2:
                figures.append(fig2)
        except Exception:
            pass
    summary = generate_summary(ranked, project_name=project_name, figures=figures)
    return summary


@mcp.tool()
def export_report(project_name: str, output_format: str = "docx",
                  report_path: str = None) -> dict:
    """Export a report to Word (.docx), PDF (.pdf), or Excel (.xlsx) format.
    If report_path not provided, looks for the latest report for this project."""
    from core.export_docs import export_docx, export_pdf, export_xlsx
    from core.utils import REPORTS_DIR, RESULTS_DIR
    import glob

    if not report_path:
        report_path = str(REPORTS_DIR / f"{project_name}_summary.md")

    if output_format in ("docx", "pdf"):
        with open(report_path) as f:
            md_text = f.read()
        if output_format == "docx":
            path = export_docx(md_text, title=f"MoleCopilot Report: {project_name}")
        else:
            path = export_pdf(md_text, title=f"MoleCopilot Report: {project_name}")
    elif output_format == "xlsx":
        import pandas as pd
        results_path = Path(str(RESULTS_DIR)) / project_name
        data = {}
        for csv_file in glob.glob(str(results_path / "*.csv")):
            sheet_name = Path(csv_file).stem.replace("_", " ").title()
            data[sheet_name] = pd.read_csv(csv_file).to_dict("records")
        if not data:
            data = {"Summary": [{"project": project_name, "report": report_path}]}
        path = export_xlsx(data, title=f"MoleCopilot Report: {project_name}")
    else:
        raise ValueError(f"Unsupported format: {output_format}. Use 'docx', 'pdf', or 'xlsx'.")

    return {"export_path": path, "format": output_format,
            "message": f"Report exported to {path}"}


# ============================================================
# SERVER ENTRY POINT
# ============================================================

if __name__ == "__main__":
    mcp.run()
