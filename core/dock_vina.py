#!/usr/bin/env python3
"""AutoDock Vina docking pipeline for MoleCopilot.

Performs molecular docking of prepared protein (PDBQT) and ligand (PDBQT)
files, parses energy scores, and supports batch docking of ligand libraries
with CSV result export.
"""

from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from typing import Any

from core.utils import (
    LIGANDS_DIR,
    PROTEINS_DIR,
    RESULTS_DIR,
    ensure_dir,
    setup_logging,
)

logger = setup_logging("dock_vina")

# Regex for parsing REMARK VINA RESULT lines in output PDBQT
_VINA_RESULT_RE: re.Pattern[str] = re.compile(
    r"REMARK VINA RESULT:\s+"
    r"([-+]?\d+\.?\d*)\s+"    # affinity (kcal/mol)
    r"([-+]?\d+\.?\d*)\s+"    # RMSD lower bound
    r"([-+]?\d+\.?\d*)"       # RMSD upper bound
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_vina_results(pdbqt_path: Path) -> list[dict[str, float]]:
    """Parse REMARK VINA RESULT lines from a Vina output PDBQT.

    Each matching line yields a dict with keys ``affinity``,
    ``rmsd_lb``, and ``rmsd_ub``.

    Parameters
    ----------
    pdbqt_path : Path
        Path to the Vina output PDBQT containing docked poses.

    Returns
    -------
    list[dict[str, float]]
        One entry per pose, ordered as they appear in the file
        (best energy first).
    """
    results: list[dict[str, float]] = []
    with open(str(pdbqt_path), "r", encoding="utf-8") as fh:
        for line in fh:
            match = _VINA_RESULT_RE.match(line)
            if match:
                results.append({
                    "affinity": float(match.group(1)),
                    "rmsd_lb": float(match.group(2)),
                    "rmsd_ub": float(match.group(3)),
                })
    return results


# ---------------------------------------------------------------------------
# dock
# ---------------------------------------------------------------------------

def dock(
    protein_pdbqt: str,
    ligand_pdbqt: str,
    center: tuple[float, float, float],
    box_size: tuple[float, float, float] = (25.0, 25.0, 25.0),
    exhaustiveness: int = 32,
    n_poses: int = 9,
) -> dict[str, Any]:
    """Dock a single ligand against a protein using AutoDock Vina.

    Parameters
    ----------
    protein_pdbqt : str
        Path to the prepared receptor PDBQT.
    ligand_pdbqt : str
        Path to the prepared ligand PDBQT.
    center : tuple[float, float, float]
        ``(x, y, z)`` centre of the docking search box in Angstroms.
    box_size : tuple[float, float, float]
        ``(sx, sy, sz)`` dimensions of the search box in Angstroms.
        Defaults to ``(25, 25, 25)``.
    exhaustiveness : int
        Thoroughness of the global search. Defaults to ``32``.
    n_poses : int
        Maximum number of binding poses to generate. Defaults to ``9``.

    Returns
    -------
    dict
        ``{best_energy, all_energies, output_path, n_poses, receptor,
        ligand, message}``

    Raises
    ------
    FileNotFoundError
        If either PDBQT file does not exist.
    RuntimeError
        If Vina produces no docking results.
    """
    from vina import Vina  # lazy import

    receptor_path = Path(protein_pdbqt).resolve()
    ligand_path = Path(ligand_pdbqt).resolve()

    if not receptor_path.is_file():
        raise FileNotFoundError(f"Receptor PDBQT not found: {protein_pdbqt}")
    if not ligand_path.is_file():
        raise FileNotFoundError(f"Ligand PDBQT not found: {ligand_pdbqt}")

    out_dir = ensure_dir(RESULTS_DIR)
    output_stem = f"{receptor_path.stem}_{ligand_path.stem}_docked"
    output_path = out_dir / f"{output_stem}.pdbqt"

    logger.info(
        "Docking %s vs %s | centre=(%.1f, %.1f, %.1f) | "
        "box=(%.1f, %.1f, %.1f) | exhaustiveness=%d",
        ligand_path.name,
        receptor_path.name,
        center[0], center[1], center[2],
        box_size[0], box_size[1], box_size[2],
        exhaustiveness,
    )

    # ── Vina docking ────────────────────────────────────────────────────
    t0 = time.time()

    v = Vina(sf_name="vina")
    v.set_receptor(str(receptor_path))
    v.set_ligand_from_file(str(ligand_path))
    v.compute_vina_maps(center=list(center), box_size=list(box_size))
    v.dock(exhaustiveness=exhaustiveness, n_poses=n_poses)
    v.write_poses(str(output_path), n_poses=n_poses, overwrite=True)

    elapsed = time.time() - t0
    logger.info("Docking completed in %.1f seconds", elapsed)

    # ── Parse results ───────────────────────────────────────────────────
    results = _parse_vina_results(output_path)

    if not results:
        raise RuntimeError(
            f"Vina produced no REMARK VINA RESULT lines in {output_path}"
        )

    all_energies = [r["affinity"] for r in results]
    best_energy = all_energies[0]

    message = (
        f"Docking complete: {len(results)} poses, "
        f"best energy = {best_energy:.2f} kcal/mol "
        f"({elapsed:.1f}s)"
    )
    logger.info(message)

    return {
        "best_energy": best_energy,
        "all_energies": all_energies,
        "all_poses": results,  # [{affinity, rmsd_lb, rmsd_ub}, ...]
        "output_path": str(output_path),
        "n_poses": len(results),
        "receptor": str(receptor_path),
        "ligand": str(ligand_path),
        "message": message,
    }


# ---------------------------------------------------------------------------
# batch_dock
# ---------------------------------------------------------------------------

def batch_dock(
    protein_pdbqt: str,
    ligand_dir: str,
    center: tuple[float, float, float],
    box_size: tuple[float, float, float] = (25.0, 25.0, 25.0),
    exhaustiveness: int = 32,
) -> dict[str, Any]:
    """Dock all PDBQT ligands in a directory against a single receptor.

    Results are saved to a CSV file sorted by binding energy (best first).

    Parameters
    ----------
    protein_pdbqt : str
        Path to the prepared receptor PDBQT.
    ligand_dir : str
        Directory containing ligand PDBQT files.
    center : tuple[float, float, float]
        ``(x, y, z)`` centre of the docking search box.
    box_size : tuple[float, float, float]
        ``(sx, sy, sz)`` dimensions of the search box.
        Defaults to ``(25, 25, 25)``.
    exhaustiveness : int
        Thoroughness of the global search. Defaults to ``32``.

    Returns
    -------
    dict
        ``{results_csv, top_hits, total, message}``
    """
    lig_dir = Path(ligand_dir).resolve()
    if not lig_dir.is_dir():
        raise FileNotFoundError(f"Ligand directory not found: {ligand_dir}")

    receptor_path = Path(protein_pdbqt).resolve()
    if not receptor_path.is_file():
        raise FileNotFoundError(f"Receptor PDBQT not found: {protein_pdbqt}")

    # Collect ligand PDBQT files
    ligand_files: list[Path] = sorted(
        p for p in lig_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdbqt"
    )

    total = len(ligand_files)
    if total == 0:
        return {
            "results_csv": "",
            "top_hits": [],
            "total": 0,
            "message": f"No .pdbqt files found in {ligand_dir}",
        }

    logger.info(
        "Batch docking: %d ligands vs %s", total, receptor_path.name
    )

    # ── Dock each ligand ────────────────────────────────────────────────
    all_results: list[dict[str, Any]] = []
    failed_count: int = 0

    for idx, lig_file in enumerate(ligand_files, 1):
        logger.info("[%d/%d] Docking %s ...", idx, total, lig_file.name)
        try:
            result = dock(
                protein_pdbqt=str(receptor_path),
                ligand_pdbqt=str(lig_file),
                center=center,
                box_size=box_size,
                exhaustiveness=exhaustiveness,
            )
            all_results.append({
                "ligand": lig_file.name,
                "best_energy": result["best_energy"],
                "n_poses": result["n_poses"],
                "output_path": result["output_path"],
            })
        except Exception as exc:
            logger.error("Failed to dock %s: %s", lig_file.name, exc)
            all_results.append({
                "ligand": lig_file.name,
                "best_energy": float("nan"),
                "n_poses": 0,
                "output_path": "",
                "error": str(exc),
            })
            failed_count += 1

    # ── Sort by energy (best = most negative first) ─────────────────────
    # NaN values sort to the end
    import math

    all_results.sort(
        key=lambda r: r["best_energy"] if not math.isnan(r["best_energy"]) else float("inf")
    )

    # ── Write CSV ───────────────────────────────────────────────────────
    out_dir = ensure_dir(RESULTS_DIR)
    csv_path = out_dir / f"{receptor_path.stem}_batch_results.csv"

    fieldnames = ["rank", "ligand", "best_energy", "n_poses", "output_path"]
    with open(str(csv_path), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for rank, row in enumerate(all_results, 1):
            writer.writerow({
                "rank": rank,
                "ligand": row["ligand"],
                "best_energy": row["best_energy"],
                "n_poses": row["n_poses"],
                "output_path": row["output_path"],
            })

    logger.info("Results CSV written: %s", csv_path)

    # ── Top hits (up to 10, excluding failures) ─────────────────────────
    top_hits: list[dict[str, Any]] = [
        {
            "rank": i + 1,
            "ligand": r["ligand"],
            "best_energy": r["best_energy"],
            "n_poses": r["n_poses"],
        }
        for i, r in enumerate(all_results)
        if not math.isnan(r["best_energy"])
    ][:10]

    message = (
        f"Batch docking complete: {total - failed_count} succeeded, "
        f"{failed_count} failed out of {total}. "
        f"Results saved to {csv_path.name}"
    )
    logger.info(message)

    return {
        "results_csv": str(csv_path),
        "top_hits": top_hits,
        "total": total,
        "message": message,
    }


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    # Look for test files
    test_receptor = PROTEINS_DIR / "3S7S_clean.pdbqt"
    test_ligand = LIGANDS_DIR / "ligand_f65b2fec.pdbqt"  # aspirin from prep_ligand demo

    if test_receptor.is_file() and test_ligand.is_file():
        print("=== Single Docking Demo ===")
        print(f"Receptor: {test_receptor.name}")
        print(f"Ligand:   {test_ligand.name}\n")

        # Use a generic centre; in real use, get this from detect_binding_site
        result = dock(
            protein_pdbqt=str(test_receptor),
            ligand_pdbqt=str(test_ligand),
            center=(0.0, 0.0, 0.0),
            box_size=(25.0, 25.0, 25.0),
            exhaustiveness=8,  # fast for demo
            n_poses=5,
        )
        print(json.dumps(result, indent=2))
    else:
        missing: list[str] = []
        if not test_receptor.is_file():
            missing.append(f"  Receptor: {test_receptor}")
        if not test_ligand.is_file():
            missing.append(f"  Ligand:   {test_ligand}")

        print(
            "=== Docking Demo ===\n"
            "Test files not found:\n"
            + "\n".join(missing)
            + "\n\n"
            "Run these first:\n"
            "  python -m scripts.prep_protein   (to prepare receptor)\n"
            "  python -m scripts.prep_ligand    (to prepare ligand)\n"
            "  python -m scripts.dock_vina      (then re-run this)",
            file=sys.stderr,
        )
        sys.exit(1)
