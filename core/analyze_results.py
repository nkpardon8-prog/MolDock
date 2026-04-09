"""
Docking result analysis and report generation for MoleCopilot.

Parses Vina output files, identifies protein-ligand interactions via PLIP,
and generates comprehensive Markdown summary reports.
"""

from pathlib import Path
from typing import Optional
import re
import datetime

from core.utils import (
    setup_logging,
    RESULTS_DIR,
    REPORTS_DIR,
    ensure_dir,
    pdbqt_to_pdb,
    merge_protein_ligand,
)

logger = setup_logging("analyze_results")


# ── Public functions ─────────────────────────────────────────────────────────


def rank_results(results_dir: str) -> dict:
    """Parse and rank all docked PDBQT files in *results_dir* by binding energy.

    Looks for files matching ``*_docked.pdbqt`` and extracts the first
    ``REMARK VINA RESULT`` line from each (lowest-energy pose).

    Parameters
    ----------
    results_dir : str
        Directory containing docked PDBQT output files.

    Returns
    -------
    dict
        Keys: csv_path (str), rankings (list[dict]), best (dict),
        message (str).
    """
    import csv

    rdir: Path = Path(results_dir)
    if not rdir.is_dir():
        logger.error("Results directory not found: %s", results_dir)
        return {
            "csv_path": "",
            "rankings": [],
            "best": {},
            "message": f"Directory not found: {results_dir}",
        }

    pdbqt_files: list[Path] = sorted(rdir.glob("*_docked.pdbqt"))
    if not pdbqt_files:
        logger.warning("No *_docked.pdbqt files found in %s", results_dir)
        return {
            "csv_path": "",
            "rankings": [],
            "best": {},
            "message": f"No docked PDBQT files found in {results_dir}",
        }

    vina_pattern = re.compile(
        r"^REMARK\s+VINA\s+RESULT:\s+"
        r"([-+]?\d+\.?\d*)\s+"
        r"([-+]?\d+\.?\d*)\s+"
        r"([-+]?\d+\.?\d*)"
    )

    rankings: list[dict] = []

    for pdbqt_file in pdbqt_files:
        ligand_name: str = pdbqt_file.stem.replace("_docked", "")
        all_poses: list[dict] = []

        with pdbqt_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                match = vina_pattern.match(line.strip())
                if match:
                    energy: float = float(match.group(1))
                    rmsd_lb: float = float(match.group(2))
                    rmsd_ub: float = float(match.group(3))
                    all_poses.append({
                        "energy": energy,
                        "rmsd_lb": rmsd_lb,
                        "rmsd_ub": rmsd_ub,
                    })

        if not all_poses:
            logger.warning("No VINA RESULT lines in %s", pdbqt_file.name)
            continue

        best_pose: dict = min(all_poses, key=lambda p: p["energy"])

        rankings.append({
            "name": ligand_name,
            "file": str(pdbqt_file),
            "binding_energy": best_pose["energy"],
            "rmsd_lb": best_pose["rmsd_lb"],
            "rmsd_ub": best_pose["rmsd_ub"],
            "num_poses": len(all_poses),
        })

    # Sort by binding energy (most negative = best)
    rankings.sort(key=lambda r: r["binding_energy"])

    # Save CSV
    csv_dir: Path = ensure_dir(RESULTS_DIR)
    csv_path: Path = csv_dir / "docking_rankings.csv"

    fieldnames: list[str] = [
        "rank",
        "name",
        "binding_energy",
        "rmsd_lb",
        "rmsd_ub",
        "num_poses",
        "file",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rank_idx, entry in enumerate(rankings, start=1):
            row = {**entry, "rank": rank_idx}
            writer.writerow(row)

    logger.info("Rankings saved to %s (%d compounds)", str(csv_path), len(rankings))

    best: dict = rankings[0] if rankings else {}
    message: str = (
        f"Ranked {len(rankings)} compounds. "
        f"Best: {best.get('name', 'N/A')} "
        f"({best.get('binding_energy', 'N/A')} kcal/mol)"
        if rankings
        else "No results to rank."
    )

    return {
        "csv_path": str(csv_path),
        "rankings": rankings,
        "best": best,
        "message": message,
    }


def _distance_fallback_interactions(
    merged_pdb_path: str,
    distance_cutoff: float = 3.5,
) -> dict:
    """Heuristic interaction detection based on atom-pair distances.

    Reads ATOM (protein) and HETATM (ligand) records from a merged PDB,
    then reports pairs closer than *distance_cutoff* angstroms.

    Parameters
    ----------
    merged_pdb_path : str
        Path to the merged complex PDB file.
    distance_cutoff : float
        Maximum distance in angstroms to consider as an interaction.

    Returns
    -------
    dict
        Interaction summary dict compatible with get_interactions output.
    """
    import math

    protein_atoms: list[dict] = []
    ligand_atoms: list[dict] = []

    with open(merged_pdb_path, "r", encoding="utf-8") as fh:
        for line in fh:
            record: str = line[:6].strip()
            if record not in ("ATOM", "HETATM"):
                continue

            try:
                x: float = float(line[30:38])
                y: float = float(line[38:46])
                z: float = float(line[46:54])
                atom_name: str = line[12:16].strip()
                res_name: str = line[17:20].strip()
                chain: str = line[21:22].strip()
                res_seq: str = line[22:26].strip()
            except (ValueError, IndexError):
                continue

            atom_info: dict = {
                "atom_name": atom_name,
                "res_name": res_name,
                "chain": chain,
                "res_seq": res_seq,
                "x": x,
                "y": y,
                "z": z,
            }

            if record == "ATOM":
                protein_atoms.append(atom_info)
            else:
                ligand_atoms.append(atom_info)

    contacts: list[dict] = []
    cutoff_sq: float = distance_cutoff * distance_cutoff

    for latom in ligand_atoms:
        for patom in protein_atoms:
            dx: float = latom["x"] - patom["x"]
            dy: float = latom["y"] - patom["y"]
            dz: float = latom["z"] - patom["z"]
            dist_sq: float = dx * dx + dy * dy + dz * dz
            if dist_sq < cutoff_sq:
                dist: float = round(math.sqrt(dist_sq), 2)
                contacts.append({
                    "protein_atom": patom["atom_name"],
                    "protein_residue": f"{patom['res_name']}{patom['res_seq']}",
                    "protein_chain": patom["chain"],
                    "ligand_atom": latom["atom_name"],
                    "ligand_residue": latom["res_name"],
                    "distance": dist,
                    "type": "close_contact",
                })

    # De-duplicate by residue-level contacts and sort by distance
    contacts.sort(key=lambda c: c["distance"])

    logger.info(
        "Distance fallback found %d close contacts (< %.1f A)",
        len(contacts),
        distance_cutoff,
    )

    return {
        "hydrogen_bonds": [],
        "hydrophobic_contacts": contacts,
        "pi_stacking": [],
        "salt_bridges": [],
        "water_bridges": [],
        "halogen_bonds": [],
        "total_interactions": len(contacts),
        "method": "distance_fallback",
        "summary": (
            f"Distance-based heuristic: {len(contacts)} close contacts "
            f"within {distance_cutoff} A (PLIP unavailable or returned no results)."
        ),
    }


def get_interactions(protein_pdb: str, ligand_path: str) -> dict:
    """Identify protein-ligand interactions for a docked pose.

    If the ligand is in PDBQT format it is automatically converted to PDB.
    The protein and ligand are then merged (ligand atoms written as HETATM)
    and analysed with PLIP.  If PLIP is unavailable or returns no
    interactions, a distance-based fallback heuristic is used.

    Parameters
    ----------
    protein_pdb : str
        Path to the protein PDB file.
    ligand_path : str
        Path to the ligand file (PDB or PDBQT).

    Returns
    -------
    dict
        Keys: hydrogen_bonds, hydrophobic_contacts, pi_stacking,
        salt_bridges, water_bridges, halogen_bonds, total_interactions,
        summary.
    """
    protein_p: Path = Path(protein_pdb)
    ligand_p: Path = Path(ligand_path)

    if not protein_p.is_file():
        logger.error("Protein PDB not found: %s", protein_pdb)
        return {
            "hydrogen_bonds": [],
            "hydrophobic_contacts": [],
            "pi_stacking": [],
            "salt_bridges": [],
            "water_bridges": [],
            "halogen_bonds": [],
            "total_interactions": 0,
            "summary": f"Error: protein file not found: {protein_pdb}",
        }

    if not ligand_p.is_file():
        logger.error("Ligand file not found: %s", ligand_path)
        return {
            "hydrogen_bonds": [],
            "hydrophobic_contacts": [],
            "pi_stacking": [],
            "salt_bridges": [],
            "water_bridges": [],
            "halogen_bonds": [],
            "total_interactions": 0,
            "summary": f"Error: ligand file not found: {ligand_path}",
        }

    # Convert PDBQT to PDB if necessary
    ligand_pdb_path: str = ligand_path
    if ligand_p.suffix.lower() == ".pdbqt":
        logger.info("Converting ligand PDBQT to PDB: %s", ligand_path)
        ligand_pdb_path = pdbqt_to_pdb(ligand_path)

    # Merge protein + ligand into a single complex PDB
    merged_name: str = f"{protein_p.stem}_{Path(ligand_pdb_path).stem}_complex.pdb"
    merged_output: str = str(ensure_dir(RESULTS_DIR) / merged_name)
    merged_path: str = merge_protein_ligand(
        protein_pdb, ligand_pdb_path, output_path=merged_output
    )
    logger.info("Merged complex for interaction analysis: %s", merged_path)

    # Try PLIP analysis
    try:
        from plip.structure.preparation import PDBComplex

        complex_obj = PDBComplex()
        complex_obj.load_pdb(merged_path)
        complex_obj.analyze()

        hydrogen_bonds: list[dict] = []
        hydrophobic_contacts: list[dict] = []
        pi_stacking: list[dict] = []
        salt_bridges: list[dict] = []
        water_bridges: list[dict] = []
        halogen_bonds: list[dict] = []

        interaction_sets = complex_obj.interaction_sets

        if not interaction_sets:
            logger.warning(
                "PLIP returned no interaction sets for %s; "
                "falling back to distance-based heuristic.",
                merged_path,
            )
            return _distance_fallback_interactions(merged_path)

        for bsid, interactions in interaction_sets.items():
            het_id: str = bsid[0] if isinstance(bsid, tuple) else str(bsid)

            # Hydrogen bonds (ligand-donor + protein-donor)
            all_hbonds = list(interactions.hbonds_ldon) + list(interactions.hbonds_pdon)
            for hb in all_hbonds:
                hydrogen_bonds.append({
                    "donor_atom": hb.d.type if hasattr(hb.d, "type") else str(hb.d),
                    "acceptor_atom": hb.a.type if hasattr(hb.a, "type") else str(hb.a),
                    "donor_residue": f"{hb.restype}{hb.resnr}",
                    "distance_da": round(hb.dist_d_a, 2) if hasattr(hb, "dist_d_a") else 0.0,
                    "distance_ha": round(hb.dist_h_a, 2) if hasattr(hb, "dist_h_a") else 0.0,
                    "angle": round(hb.angle, 1) if hasattr(hb, "angle") else 0.0,
                    "is_protein_donor": hb.protisdon if hasattr(hb, "protisdon") else False,
                    "het_id": het_id,
                })

            # Hydrophobic contacts
            for hc in interactions.hydrophobic_contacts:
                hydrophobic_contacts.append({
                    "protein_atom": hc.bsatom.type if hasattr(hc.bsatom, "type") else str(hc.bsatom),
                    "ligand_atom": hc.ligatom.type if hasattr(hc.ligatom, "type") else str(hc.ligatom),
                    "residue": f"{hc.restype}{hc.resnr}",
                    "distance": round(hc.distance, 2) if hasattr(hc, "distance") else 0.0,
                    "het_id": het_id,
                })

            # Pi-stacking
            for ps in interactions.pistacking:
                pi_stacking.append({
                    "residue": f"{ps.restype}{ps.resnr}",
                    "type": ps.type if hasattr(ps, "type") else "unknown",
                    "distance": round(ps.distance, 2) if hasattr(ps, "distance") else 0.0,
                    "angle": round(ps.angle, 1) if hasattr(ps, "angle") else 0.0,
                    "het_id": het_id,
                })

            # Salt bridges
            for sb in interactions.saltbridge_lneg + interactions.saltbridge_pneg:
                salt_bridges.append({
                    "residue": f"{sb.restype}{sb.resnr}",
                    "distance": round(sb.distance, 2) if hasattr(sb, "distance") else 0.0,
                    "is_protein_positive": sb.protispos if hasattr(sb, "protispos") else False,
                    "het_id": het_id,
                })

            # Water bridges
            for wb in interactions.water_bridges:
                water_bridges.append({
                    "residue": f"{wb.restype}{wb.resnr}",
                    "distance_aw": round(wb.distance_aw, 2) if hasattr(wb, "distance_aw") else 0.0,
                    "distance_dw": round(wb.distance_dw, 2) if hasattr(wb, "distance_dw") else 0.0,
                    "angle": round(wb.d_angle, 1) if hasattr(wb, "d_angle") else 0.0,
                    "het_id": het_id,
                })

            # Halogen bonds
            for xb in interactions.halogen_bonds:
                halogen_bonds.append({
                    "residue": f"{xb.restype}{xb.resnr}",
                    "donor_atom": xb.don.type if hasattr(xb.don, "type") else str(xb.don),
                    "acceptor_atom": xb.acc.type if hasattr(xb.acc, "type") else str(xb.acc),
                    "distance": round(xb.distance, 2) if hasattr(xb, "distance") else 0.0,
                    "het_id": het_id,
                })

        total: int = (
            len(hydrogen_bonds)
            + len(hydrophobic_contacts)
            + len(pi_stacking)
            + len(salt_bridges)
            + len(water_bridges)
            + len(halogen_bonds)
        )

        parts: list[str] = []
        if hydrogen_bonds:
            parts.append(f"{len(hydrogen_bonds)} H-bonds")
        if hydrophobic_contacts:
            parts.append(f"{len(hydrophobic_contacts)} hydrophobic")
        if pi_stacking:
            parts.append(f"{len(pi_stacking)} pi-stacking")
        if salt_bridges:
            parts.append(f"{len(salt_bridges)} salt bridges")
        if water_bridges:
            parts.append(f"{len(water_bridges)} water bridges")
        if halogen_bonds:
            parts.append(f"{len(halogen_bonds)} halogen bonds")

        summary_str: str = (
            f"PLIP analysis: {total} interactions ({', '.join(parts)})"
            if parts
            else "PLIP analysis: no interactions detected"
        )

        return {
            "hydrogen_bonds": hydrogen_bonds,
            "hydrophobic_contacts": hydrophobic_contacts,
            "pi_stacking": pi_stacking,
            "salt_bridges": salt_bridges,
            "water_bridges": water_bridges,
            "halogen_bonds": halogen_bonds,
            "total_interactions": total,
            "method": "plip",
            "summary": summary_str,
        }

    except ImportError:
        logger.warning("PLIP not available; using distance-based fallback.")
        return _distance_fallback_interactions(merged_path)
    except Exception as exc:
        logger.error("PLIP analysis failed: %s; using fallback.", exc)
        return _distance_fallback_interactions(merged_path)


def interaction_fingerprint(protein_pdb: str, ligand_pdb: str) -> dict:
    """Generate a ProLIF interaction fingerprint for a protein-ligand complex.

    ProLIF is an optional dependency. If unavailable, an empty result
    with a warning is returned.

    Parameters
    ----------
    protein_pdb : str
        Path to the protein PDB file.
    ligand_pdb : str
        Path to the ligand PDB file.

    Returns
    -------
    dict
        Keys: fingerprint (list or empty), residues (list), interaction_types
        (list), available (bool), message (str).
    """
    try:
        import prolif as plf
        import MDAnalysis as mda
    except ImportError:
        logger.warning(
            "ProLIF or MDAnalysis not available; "
            "interaction fingerprint cannot be computed."
        )
        return {
            "fingerprint": [],
            "residues": [],
            "interaction_types": [],
            "available": False,
            "message": "ProLIF/MDAnalysis not installed. Install with: "
                       "pip install prolif MDAnalysis",
        }

    protein_p: Path = Path(protein_pdb)
    ligand_p: Path = Path(ligand_pdb)

    if not protein_p.is_file():
        return {
            "fingerprint": [],
            "residues": [],
            "interaction_types": [],
            "available": False,
            "message": f"Protein PDB not found: {protein_pdb}",
        }

    if not ligand_p.is_file():
        return {
            "fingerprint": [],
            "residues": [],
            "interaction_types": [],
            "available": False,
            "message": f"Ligand PDB not found: {ligand_pdb}",
        }

    try:
        # Load structures
        protein_mol = plf.Molecule.from_mda(
            mda.Universe(str(protein_p))
        )
        ligand_mol = plf.Molecule.from_mda(
            mda.Universe(str(ligand_p))
        )

        # Compute fingerprint
        fp = plf.Fingerprint()
        fp.run_from_iterable([ligand_mol], protein_mol)

        # Convert to a serializable format
        df = fp.to_dataframe()
        residues: list[str] = [str(col[0]) for col in df.columns]
        interaction_types: list[str] = [str(col[1]) for col in df.columns]
        fingerprint_bits: list[bool] = [bool(v) for v in df.iloc[0].values]

        unique_residues: list[str] = sorted(set(residues))
        unique_types: list[str] = sorted(set(interaction_types))

        fingerprint_data: list[dict] = []
        for i, (res, itype, bit) in enumerate(
            zip(residues, interaction_types, fingerprint_bits)
        ):
            if bit:
                fingerprint_data.append({
                    "residue": res,
                    "interaction_type": itype,
                })

        return {
            "fingerprint": fingerprint_data,
            "residues": unique_residues,
            "interaction_types": unique_types,
            "available": True,
            "message": (
                f"ProLIF fingerprint: {len(fingerprint_data)} interactions "
                f"across {len(unique_residues)} residues."
            ),
        }

    except Exception as exc:
        logger.error("ProLIF fingerprint generation failed: %s", exc)
        return {
            "fingerprint": [],
            "residues": [],
            "interaction_types": [],
            "available": False,
            "message": f"ProLIF analysis failed: {exc}",
        }


def generate_summary(
    docking_results: list,
    admet_results: Optional[list] = None,
    interactions: Optional[list] = None,
    project_name: str = "unnamed",
    protein_info: Optional[dict] = None,
    figures: Optional[list] = None,
) -> dict:
    """Generate a comprehensive Markdown summary report.

    Normalizes docking result keys (``best_energy`` -> ``binding_energy``),
    builds a full report with tables and analysis, and optionally auto-generates
    figures if data is sufficient.

    Parameters
    ----------
    docking_results : list
        List of docking result dicts (must have 'name'/'ligand_name' and
        'binding_energy'/'best_energy').
    admet_results : list, optional
        List of ADMET result dicts from full_admet().
    interactions : list, optional
        List of interaction dicts from get_interactions().
    project_name : str
        Project name for the report title and filename.
    protein_info : dict, optional
        Protein metadata (e.g., pdb_id, name, organism).
    figures : list, optional
        List of figure file paths to include.

    Returns
    -------
    dict
        Keys: report_path (str), markdown (str), figures (list[str]),
        message (str).
    """
    # Normalize docking results
    normalized: list[dict] = []
    for item in docking_results:
        entry: dict = dict(item)  # shallow copy, avoid mutating input
        # Normalize name
        if "name" not in entry and "ligand_name" in entry:
            entry["name"] = entry["ligand_name"]
        elif "name" not in entry:
            entry["name"] = "Unknown"
        # Normalize energy key
        if "binding_energy" not in entry and "best_energy" in entry:
            entry["binding_energy"] = entry["best_energy"]
        elif "binding_energy" not in entry:
            entry["binding_energy"] = 0.0
        normalized.append(entry)

    # Sort by binding energy
    normalized.sort(key=lambda r: r.get("binding_energy", 0.0))

    # Auto-generate figures
    generated_figures: list[str] = list(figures) if figures else []

    if len(normalized) >= 2:
        try:
            from core.generate_figures import (
                plot_binding_energies,
                plot_energy_distribution,
            )

            fig_dir: Path = ensure_dir(REPORTS_DIR / "figures")

            energy_chart: str = plot_binding_energies(
                normalized,
                output_path=str(fig_dir / f"{project_name}_binding_energies.png"),
            )
            generated_figures.append(energy_chart)

            dist_chart: str = plot_energy_distribution(
                normalized,
                output_path=str(fig_dir / f"{project_name}_energy_distribution.png"),
            )
            generated_figures.append(dist_chart)

            logger.info("Auto-generated %d figures", 2)
        except Exception as exc:
            logger.warning("Figure auto-generation failed: %s", exc)

    # Build Markdown report
    today: str = datetime.date.today().isoformat()
    lines: list[str] = []

    lines.append(f"# MoleCopilot Report: {project_name}")
    lines.append("")
    lines.append(f"**Date:** {today}")
    lines.append("")

    # Protein info
    if protein_info:
        lines.append("## Protein Target")
        lines.append("")
        for key, value in protein_info.items():
            lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
        lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    total_compounds: int = len(normalized)
    strong_binders: int = sum(
        1 for r in normalized if r.get("binding_energy", 0) <= -8.0
    )
    moderate_binders: int = sum(
        1 for r in normalized
        if -8.0 < r.get("binding_energy", 0) <= -7.0
    )
    weak_binders: int = sum(
        1 for r in normalized if r.get("binding_energy", 0) > -7.0
    )

    lines.append(f"- **Total compounds screened:** {total_compounds}")
    lines.append(
        f"- **Strong binders (< -8.0 kcal/mol):** {strong_binders}"
    )
    lines.append(
        f"- **Moderate binders (-7.0 to -8.0 kcal/mol):** {moderate_binders}"
    )
    lines.append(f"- **Weak binders (> -7.0 kcal/mol):** {weak_binders}")
    if normalized:
        best = normalized[0]
        lines.append(
            f"- **Best hit:** {best['name']} "
            f"({best['binding_energy']} kcal/mol)"
        )
    lines.append("")

    # Top hits table
    lines.append("## Top Hits")
    lines.append("")
    top_n: int = min(20, len(normalized))
    lines.append(
        "| Rank | Compound | Binding Energy (kcal/mol) | Classification |"
    )
    lines.append("|------|----------|--------------------------|----------------|")
    for i, result in enumerate(normalized[:top_n], start=1):
        energy: float = result.get("binding_energy", 0.0)
        if energy <= -8.0:
            classification = "Strong"
        elif energy <= -7.0:
            classification = "Moderate"
        else:
            classification = "Weak"
        lines.append(
            f"| {i} | {result['name']} | {energy:.1f} | {classification} |"
        )
    lines.append("")

    # ADMET profiles
    if admet_results:
        lines.append("## ADMET Profiles")
        lines.append("")
        lines.append(
            "| Compound | MW | LogP | HBD | HBA | TPSA | Score | Assessment |"
        )
        lines.append(
            "|----------|----|------|-----|-----|------|-------|------------|"
        )
        for admet in admet_results:
            name: str = admet.get("name", admet.get("smiles", "?")[:20])
            mw: float = admet.get("mw", 0)
            logp: float = admet.get("logp", 0)
            hbd: int = admet.get("hbd", 0)
            hba: int = admet.get("hba", 0)
            tpsa: float = admet.get("tpsa", 0)
            score_val: float = admet.get("drug_likeness_score", 0)
            assessment: str = admet.get("assessment", "N/A")
            lines.append(
                f"| {name} | {mw:.1f} | {logp:.2f} | {hbd} | {hba} | "
                f"{tpsa:.1f} | {score_val:.2f} | {assessment} |"
            )
        lines.append("")

    # Interaction details
    if interactions:
        lines.append("## Interaction Analysis")
        lines.append("")
        for idx, inter in enumerate(interactions):
            compound_name: str = inter.get("compound_name", f"Compound {idx + 1}")
            lines.append(f"### {compound_name}")
            lines.append("")
            lines.append(f"- **Total interactions:** {inter.get('total_interactions', 0)}")
            lines.append(f"- **Method:** {inter.get('method', 'unknown')}")
            lines.append(f"- **Summary:** {inter.get('summary', 'N/A')}")
            lines.append("")

            hbonds: list = inter.get("hydrogen_bonds", [])
            if hbonds:
                lines.append("**Hydrogen Bonds:**")
                lines.append("")
                lines.append("| Donor | Acceptor | Residue | Distance (A) |")
                lines.append("|-------|----------|---------|--------------|")
                for hb in hbonds[:10]:
                    lines.append(
                        f"| {hb.get('donor_atom', '?')} | "
                        f"{hb.get('acceptor_atom', '?')} | "
                        f"{hb.get('donor_residue', '?')} | "
                        f"{hb.get('distance_da', '?')} |"
                    )
                lines.append("")

            hydro: list = inter.get("hydrophobic_contacts", [])
            if hydro:
                lines.append(f"**Hydrophobic Contacts:** {len(hydro)}")
                lines.append("")

            pi: list = inter.get("pi_stacking", [])
            if pi:
                lines.append(f"**Pi-Stacking:** {len(pi)}")
                lines.append("")

            sb: list = inter.get("salt_bridges", [])
            if sb:
                lines.append(f"**Salt Bridges:** {len(sb)}")
                lines.append("")

    # Figure references
    if generated_figures:
        lines.append("## Figures")
        lines.append("")
        for fig_path in generated_figures:
            fig_name: str = Path(fig_path).name
            lines.append(f"![{fig_name}]({fig_path})")
            lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(
        f"*Generated by MoleCopilot on {today}.*"
    )
    lines.append("")

    markdown: str = "\n".join(lines)

    # Save report
    report_dir: Path = ensure_dir(REPORTS_DIR)
    report_path: Path = report_dir / f"{project_name}_summary.md"

    with report_path.open("w", encoding="utf-8") as fh:
        fh.write(markdown)

    logger.info("Report saved to %s", str(report_path))

    return {
        "report_path": str(report_path),
        "markdown": markdown,
        "figures": generated_figures,
        "message": f"Report generated: {report_path.name} "
                   f"({len(normalized)} compounds, "
                   f"{len(generated_figures)} figures)",
    }


# ── Standalone demo ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("MoleCopilot Results Analysis — Demo")
    print("=" * 60)

    # Demo: rank_results with mock data
    print("\n--- rank_results demo ---")
    demo_results_dir: Path = ensure_dir(RESULTS_DIR)

    # Create mock docked PDBQT files for demo
    mock_docking_data: list[tuple[str, list[str]]] = [
        (
            "aspirin_docked.pdbqt",
            [
                "REMARK VINA RESULT:    -6.5      0.000      0.000",
                "REMARK VINA RESULT:    -6.2      1.234      2.345",
                "REMARK VINA RESULT:    -5.8      2.100      3.456",
            ],
        ),
        (
            "ibuprofen_docked.pdbqt",
            [
                "REMARK VINA RESULT:    -7.8      0.000      0.000",
                "REMARK VINA RESULT:    -7.1      1.890      2.678",
            ],
        ),
        (
            "caffeine_docked.pdbqt",
            [
                "REMARK VINA RESULT:    -5.2      0.000      0.000",
                "REMARK VINA RESULT:    -4.9      0.987      1.543",
            ],
        ),
        (
            "celecoxib_docked.pdbqt",
            [
                "REMARK VINA RESULT:    -9.1      0.000      0.000",
                "REMARK VINA RESULT:    -8.7      1.456      2.234",
                "REMARK VINA RESULT:    -8.2      2.345      3.567",
            ],
        ),
        (
            "naproxen_docked.pdbqt",
            [
                "REMARK VINA RESULT:    -8.3      0.000      0.000",
                "REMARK VINA RESULT:    -7.9      1.100      1.800",
            ],
        ),
    ]

    for filename, vina_lines in mock_docking_data:
        mock_path: Path = demo_results_dir / filename
        with mock_path.open("w", encoding="utf-8") as fh:
            fh.write("MODEL        1\n")
            fh.write(f"{vina_lines[0]}\n")
            fh.write("ATOM      1  C   UNL     1       0.000   0.000   0.000\n")
            fh.write("ENDMDL\n")
            for vl in vina_lines[1:]:
                fh.write("MODEL        2\n")
                fh.write(f"{vl}\n")
                fh.write("ATOM      1  C   UNL     1       1.000   1.000   1.000\n")
                fh.write("ENDMDL\n")

    result = rank_results(str(demo_results_dir))
    print(f"  Message: {result['message']}")
    print(f"  CSV: {result['csv_path']}")
    if result["rankings"]:
        print("  Rankings:")
        for i, r in enumerate(result["rankings"], 1):
            print(f"    {i}. {r['name']}: {r['binding_energy']} kcal/mol "
                  f"({r['num_poses']} poses)")

    # Demo: generate_summary
    print("\n--- generate_summary demo ---")

    mock_docking: list[dict] = [
        {"name": "Celecoxib", "binding_energy": -9.1},
        {"name": "Naproxen", "best_energy": -8.3},
        {"name": "Ibuprofen", "ligand_name": "Ibuprofen", "binding_energy": -7.8},
        {"name": "Aspirin", "binding_energy": -6.5},
        {"name": "Caffeine", "binding_energy": -5.2},
    ]

    mock_admet: list[dict] = [
        {
            "name": "Celecoxib",
            "mw": 381.37,
            "logp": 3.53,
            "hbd": 1,
            "hba": 4,
            "tpsa": 86.36,
            "drug_likeness_score": 0.7,
            "assessment": "Good",
        },
        {
            "name": "Aspirin",
            "mw": 180.16,
            "logp": 1.31,
            "hbd": 1,
            "hba": 4,
            "tpsa": 63.6,
            "drug_likeness_score": 0.8,
            "assessment": "Excellent",
        },
    ]

    mock_interactions: list[dict] = [
        {
            "compound_name": "Celecoxib",
            "total_interactions": 8,
            "method": "plip",
            "summary": "8 interactions (3 H-bonds, 4 hydrophobic, 1 pi-stacking)",
            "hydrogen_bonds": [
                {
                    "donor_atom": "N",
                    "acceptor_atom": "O",
                    "donor_residue": "ARG513",
                    "distance_da": 2.8,
                },
            ],
            "hydrophobic_contacts": [{"residue": "PHE518"}] * 4,
            "pi_stacking": [{"residue": "TRP387"}],
            "salt_bridges": [],
        },
    ]

    summary_result = generate_summary(
        docking_results=mock_docking,
        admet_results=mock_admet,
        interactions=mock_interactions,
        project_name="demo_project",
        protein_info={
            "pdb_id": "3LN1",
            "name": "Cyclooxygenase-2 (COX-2)",
            "organism": "Mus musculus",
        },
    )

    print(f"  Report: {summary_result['report_path']}")
    print(f"  Figures: {len(summary_result['figures'])}")
    print(f"  Message: {summary_result['message']}")
    print(f"\n  First 30 lines of report:")
    for line in summary_result["markdown"].split("\n")[:30]:
        print(f"    {line}")

    # Clean up mock files
    for filename, _ in mock_docking_data:
        mock_file: Path = demo_results_dir / filename
        if mock_file.exists():
            mock_file.unlink()

    print("\nDone.")
