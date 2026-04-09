#!/usr/bin/env python3
"""Protein preparation pipeline for MoleCopilot.

Cleans PDB structures (missing residues, non-standard residues, hydrogens)
using PDBFixer/OpenMM, converts to PDBQT via Open Babel, and detects
binding sites from co-crystallised ligands using BioPython.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from core.utils import (
    PROTEINS_DIR,
    RESULTS_DIR,
    detect_file_format,
    ensure_dir,
    setup_logging,
)

logger = setup_logging("prep_protein")

# Residues to exclude when searching for co-crystallised ligands
_EXCLUDE_RESNAMES: set[str] = {
    "HOH", "WAT", "TIP", "TIP3",  # water
    "NA", "CL", "MG", "ZN", "CA", "K", "FE", "MN", "CO", "CU", "NI",  # ions
    "SO4", "PO4", "GOL", "EDO", "ACT", "DMS",  # common additives
}


# ---------------------------------------------------------------------------
# prepare_protein
# ---------------------------------------------------------------------------

def prepare_protein(pdb_path: str, output_dir: str | None = None) -> dict[str, Any]:
    """Clean a PDB file and convert it to PDBQT for docking.

    Processing order (PDBFixer):
        1. Find missing residues
        2. Find & replace non-standard residues
        3. Remove heterogens (including water)
        4. Find & add missing atoms
        5. Add missing hydrogens at pH 7.0
        6. Write cleaned PDB
        7. Convert to PDBQT via Open Babel
        8. Validate PDBQT atom-type column

    Parameters
    ----------
    pdb_path : str
        Path to the input PDB file.
    output_dir : str, optional
        Directory for output files.  Defaults to ``PROTEINS_DIR``.

    Returns
    -------
    dict
        ``{clean_pdb: str, pdbqt_path: str, message: str}``

    Raises
    ------
    FileNotFoundError
        If *pdb_path* does not exist.
    ValueError
        If the generated PDBQT fails validation.
    """
    from pdbfixer import PDBFixer
    from openmm.app import PDBFile

    src = Path(pdb_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"PDB file not found: {pdb_path}")

    out_dir = ensure_dir(Path(output_dir) if output_dir else PROTEINS_DIR)
    stem = src.stem
    clean_pdb: Path = out_dir / f"{stem}_clean.pdb"
    pdbqt_path: Path = out_dir / f"{stem}_clean.pdbqt"

    # ── PDBFixer pipeline (strict order) ────────────────────────────────
    logger.info("Loading PDB: %s", src)
    fixer = PDBFixer(filename=str(src))

    logger.info("Finding missing residues ...")
    fixer.findMissingResidues()

    logger.info("Finding non-standard residues ...")
    fixer.findNonstandardResidues()

    logger.info("Replacing non-standard residues ...")
    fixer.replaceNonstandardResidues()

    logger.info("Removing heterogens (including water) ...")
    fixer.removeHeterogens(keepWater=False)

    logger.info("Finding missing atoms ...")
    fixer.findMissingAtoms()

    logger.info("Adding missing atoms ...")
    fixer.addMissingAtoms()

    logger.info("Adding hydrogens at pH 7.0 ...")
    fixer.addMissingHydrogens(pH=7.0)

    logger.info("Writing cleaned PDB: %s", clean_pdb)
    with open(str(clean_pdb), "w", encoding="utf-8") as fh:
        PDBFile.writeFile(fixer.topology, fixer.positions, fh)

    # ── Open Babel: PDB → PDBQT ────────────────────────────────────────
    logger.info("Converting to PDBQT via Open Babel ...")
    from openbabel import pybel  # noqa: E402  (lazy import)

    mol = next(pybel.readfile("pdb", str(clean_pdb)))
    mol.write("pdbqt", str(pdbqt_path), overwrite=True)
    logger.info("PDBQT written: %s", pdbqt_path)

    # ── Strip ligand-style tags from receptor PDBQT ──────────────────────
    # Open Babel may write ROOT/ENDROOT/BRANCH/ENDBRANCH/TORSDOF tags
    # which are valid only for ligand PDBQTs. Vina rejects them in receptors.
    _strip_ligand_tags(pdbqt_path)
    logger.info("Stripped ligand-style tags from receptor PDBQT")

    # ── Validate PDBQT atom types (columns 77-79) ──────────────────────
    _validate_pdbqt(pdbqt_path)

    message = (
        f"Prepared {stem}: cleaned PDB ({clean_pdb.name}) "
        f"and PDBQT ({pdbqt_path.name})"
    )
    logger.info(message)

    return {
        "clean_pdb": str(clean_pdb),
        "pdbqt_path": str(pdbqt_path),
        "message": message,
    }


def _strip_ligand_tags(pdbqt_path: Path) -> None:
    """Remove ROOT/ENDROOT/BRANCH/ENDBRANCH/TORSDOF lines from a receptor PDBQT.

    Open Babel sometimes writes these ligand-specific tags when converting
    proteins to PDBQT.  AutoDock Vina rejects them in rigid receptors with
    ``PDBQT parsing error: Unknown or inappropriate tag found``.

    Note: Open Babel may concatenate tag and numbers (e.g. ``BRANCH10001001``
    instead of ``BRANCH   1000  1001``), so we match by prefix, not by split.
    """
    ligand_prefixes = ("ROOT", "ENDROOT", "BRANCH", "ENDBRANCH", "TORSDOF")
    lines = pdbqt_path.read_text().splitlines(keepends=True)
    cleaned = [
        line for line in lines
        if not line.strip().startswith(ligand_prefixes)
    ]
    pdbqt_path.write_text("".join(cleaned))


def _validate_pdbqt(pdbqt_path: Path) -> None:
    """Check that ATOM/HETATM lines in a PDBQT carry atom-type annotations.

    PDBQT extends PDB format by storing the AutoDock atom type in columns
    77-79 (0-indexed 77:80).  This function reads the file back and
    verifies that at least one such type is present.

    Raises
    ------
    ValueError
        If no atom-type annotations are found.
    """
    found_types: int = 0
    total_atoms: int = 0
    with open(str(pdbqt_path), "r", encoding="utf-8") as fh:
        for line in fh:
            record = line[:6].strip()
            if record in ("ATOM", "HETATM"):
                total_atoms += 1
                # Atom type lives in columns 77-79 (1-indexed col 78-80)
                if len(line) >= 78:
                    atom_type = line[77:80].strip()
                    if atom_type:
                        found_types += 1

    if total_atoms == 0:
        raise ValueError(
            f"PDBQT file contains no ATOM/HETATM records: {pdbqt_path}"
        )

    if found_types == 0:
        raise ValueError(
            f"PDBQT validation failed: {total_atoms} atom records found "
            f"but none contain atom-type annotations in columns 77-79. "
            f"File: {pdbqt_path}"
        )

    logger.info(
        "PDBQT validation passed: %d/%d atoms have type annotations",
        found_types,
        total_atoms,
    )


# ---------------------------------------------------------------------------
# detect_binding_site
# ---------------------------------------------------------------------------

def detect_binding_site(
    pdb_path: str,
    ligand_resname: str | None = None,
) -> dict[str, Any]:
    """Identify the binding site from co-crystallised heteroatoms.

    **Must be called on the original PDB** before ``prepare_protein``
    removes heterogens.

    Strategy:
        1. Parse all HETATM records via BioPython.
        2. Exclude water and common ions/additives.
        3. If *ligand_resname* is given, use that residue.
           Otherwise pick the largest remaining HETATM group.
        4. Compute centre of mass, bounding box, and add 5 A padding.
        5. If no suitable HETATM found, fall back to protein centre
           of mass with a 30x30x30 A box.
        6. Collect residues within 6 A of the centre.

    Parameters
    ----------
    pdb_path : str
        Path to the **original** (un-cleaned) PDB file.
    ligand_resname : str, optional
        Three-letter residue name of the target ligand (e.g. ``"ATP"``).

    Returns
    -------
    dict
        Keys: ``center_x``, ``center_y``, ``center_z``,
        ``size_x``, ``size_y``, ``size_z``,
        ``ligand_found`` (bool), ``ligand_resname`` (str),
        ``residues_nearby`` (list of str).
    """
    from Bio.PDB import PDBParser  # lazy import
    import numpy as np  # lazy import

    src = Path(pdb_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"PDB file not found: {pdb_path}")

    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("protein", str(src))

    # ── Collect HETATM candidates ───────────────────────────────────────
    # Group HETATM atoms by (chain_id, resname, resseq)
    het_groups: dict[tuple[str, str, int], list[np.ndarray]] = {}
    for model in structure:
        for chain in model:
            for residue in chain:
                hetflag = residue.get_id()[0]
                if hetflag.startswith("H_") or hetflag == "W":
                    resname = residue.get_resname().strip()
                    if resname in _EXCLUDE_RESNAMES:
                        continue
                    key = (chain.get_id(), resname, residue.get_id()[1])
                    coords = [atom.get_vector().get_array() for atom in residue]
                    if coords:
                        het_groups[key] = [np.array(c) for c in coords]

    # ── Select target ligand ────────────────────────────────────────────
    ligand_coords: list[np.ndarray] = []
    found_resname: str = ""
    ligand_found: bool = False

    if ligand_resname:
        # Find matching residue(s)
        for (cid, rname, rseq), coords in het_groups.items():
            if rname == ligand_resname.strip().upper():
                ligand_coords.extend(coords)
                found_resname = rname
        if ligand_coords:
            ligand_found = True
            logger.info(
                "Found specified ligand %s with %d atoms",
                found_resname,
                len(ligand_coords),
            )
        else:
            logger.warning(
                "Specified ligand '%s' not found among HETATM records",
                ligand_resname,
            )

    if not ligand_coords and het_groups:
        # Pick the largest HETATM group by atom count
        best_key = max(het_groups, key=lambda k: len(het_groups[k]))
        ligand_coords = het_groups[best_key]
        found_resname = best_key[1]
        ligand_found = True
        logger.info(
            "Auto-detected ligand %s (chain %s, resseq %d) with %d atoms",
            found_resname,
            best_key[0],
            best_key[2],
            len(ligand_coords),
        )

    # ── Compute centre and box ──────────────────────────────────────────
    if ligand_coords:
        all_coords = np.array(ligand_coords)
        center = all_coords.mean(axis=0)
        mins = all_coords.min(axis=0)
        maxs = all_coords.max(axis=0)
        padding = 5.0
        box_size = (maxs - mins) + 2 * padding
        # Enforce minimum box size of 10 A per dimension
        box_size = np.maximum(box_size, 10.0)
    else:
        # Fallback: protein centre of mass with 30x30x30 box
        logger.warning(
            "No suitable HETATM found. Using protein centre of mass "
            "with 30x30x30 A box."
        )
        all_protein_coords: list[np.ndarray] = []
        for model in structure:
            for chain in model:
                for residue in chain:
                    for atom in residue:
                        all_protein_coords.append(
                            np.array(atom.get_vector().get_array())
                        )
        if not all_protein_coords:
            raise ValueError("PDB contains no atoms at all")
        arr = np.array(all_protein_coords)
        center = arr.mean(axis=0)
        box_size = np.array([30.0, 30.0, 30.0])
        found_resname = ""
        ligand_found = False

    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
    sx, sy, sz = float(box_size[0]), float(box_size[1]), float(box_size[2])

    # ── Find nearby residues (within 6 A of centre) ────────────────────
    nearby_residues: list[str] = []
    cutoff = 6.0
    center_vec = center
    for model in structure:
        for chain in model:
            for residue in chain:
                hetflag = residue.get_id()[0]
                # Only standard residues (not hetero, not water)
                if hetflag != " ":
                    continue
                for atom in residue:
                    coord = np.array(atom.get_vector().get_array())
                    dist = float(np.linalg.norm(coord - center_vec))
                    if dist <= cutoff:
                        resname = residue.get_resname().strip()
                        resseq = residue.get_id()[1]
                        chain_id = chain.get_id()
                        label = f"{chain_id}:{resname}{resseq}"
                        if label not in nearby_residues:
                            nearby_residues.append(label)
                        break  # one atom is enough to include the residue

    nearby_residues.sort()
    logger.info(
        "Binding site: centre (%.2f, %.2f, %.2f), "
        "box (%.1f, %.1f, %.1f), %d nearby residues",
        cx, cy, cz, sx, sy, sz, len(nearby_residues),
    )

    return {
        "center_x": round(cx, 3),
        "center_y": round(cy, 3),
        "center_z": round(cz, 3),
        "size_x": round(sx, 1),
        "size_y": round(sy, 1),
        "size_z": round(sz, 1),
        "ligand_found": ligand_found,
        "ligand_resname": found_resname,
        "residues_nearby": nearby_residues,
    }


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    demo_pdb = PROTEINS_DIR / "3S7S.pdb"

    if demo_pdb.is_file():
        print(f"=== Binding-site detection (original PDB) ===")
        site = detect_binding_site(str(demo_pdb))
        print(json.dumps(site, indent=2))

        print(f"\n=== Protein preparation ===")
        result = prepare_protein(str(demo_pdb))
        print(json.dumps(result, indent=2))
    else:
        print(
            f"Demo PDB not found at {demo_pdb}.\n"
            f"Download it first:\n"
            f"  curl -o {demo_pdb} https://files.rcsb.org/download/3S7S.pdb",
            file=sys.stderr,
        )
        sys.exit(1)
