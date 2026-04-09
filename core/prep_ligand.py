#!/usr/bin/env python3
"""Ligand preparation pipeline for MoleCopilot.

Converts small-molecule inputs (SMILES strings, SDF, MOL2, PDB files) into
PDBQT format suitable for AutoDock Vina docking.  Primary method uses
RDKit + Meeko; falls back to Open Babel when Meeko fails.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import (
    LIGANDS_DIR,
    detect_file_format,
    ensure_dir,
    setup_logging,
    validate_smiles,
)

logger = setup_logging("prep_ligand")

# File extensions we recognise as molecular structure files
_STRUCTURE_EXTENSIONS: set[str] = {".sdf", ".mol2", ".pdb", ".mol", ".xyz"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _smiles_to_sdf(smiles: str, output_path: Path) -> Path:
    """Convert a SMILES string to a 3-D SDF file via RDKit.

    Performs 2-D → 3-D coordinate generation with the ETKDG method
    and a UFF force-field energy minimisation.

    Parameters
    ----------
    smiles : str
        Valid SMILES string.
    output_path : Path
        Where to write the resulting ``.sdf`` file.

    Returns
    -------
    Path
        *output_path* after the file has been written.

    Raises
    ------
    ValueError
        If RDKit cannot parse the SMILES or embedding fails.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles}")

    mol = Chem.AddHs(mol)

    # 3-D embedding with ETKDG
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    embed_result = AllChem.EmbedMolecule(mol, params)
    if embed_result != 0:
        # Retry without distance-geometry constraints
        logger.warning("ETKDG embedding failed, retrying with random coords")
        params.useRandomCoords = True
        embed_result = AllChem.EmbedMolecule(mol, params)
        if embed_result != 0:
            raise ValueError(f"RDKit 3-D embedding failed for: {smiles}")

    # Minimise with UFF
    try:
        AllChem.UFFOptimizeMolecule(mol, maxIters=500)
    except Exception as exc:
        logger.warning("UFF minimisation failed (non-fatal): %s", exc)

    writer = Chem.SDWriter(str(output_path))
    writer.write(mol)
    writer.close()
    logger.info("SMILES → SDF: %s", output_path.name)
    return output_path


def _read_molecule_rdkit(file_path: Path, fmt: str) -> Any:
    """Read a single molecule from *file_path* using RDKit.

    Parameters
    ----------
    file_path : Path
        Input molecular-structure file.
    fmt : str
        File format (``"sdf"``, ``"mol2"``, ``"pdb"``).

    Returns
    -------
    rdkit.Chem.Mol or None
        The first molecule from the file, or ``None`` on failure.
    """
    from rdkit import Chem

    readers: dict[str, Any] = {
        "sdf": lambda p: next(Chem.SDMolSupplier(str(p), removeHs=False), None),
        "mol": lambda p: next(Chem.SDMolSupplier(str(p), removeHs=False), None),
        "mol2": lambda p: Chem.MolFromMol2File(str(p), removeHs=False),
        "pdb": lambda p: Chem.MolFromPDBFile(str(p), removeHs=False),
    }

    reader = readers.get(fmt)
    if reader is None:
        return None
    try:
        mol = reader(file_path)
        return mol
    except Exception as exc:
        logger.warning("RDKit read failed for %s: %s", file_path, exc)
        return None


def _prepare_via_meeko(mol: Any, output_path: Path) -> str:
    """Convert an RDKit Mol to PDBQT using Meeko.

    Parameters
    ----------
    mol : rdkit.Chem.Mol
        Input molecule with 3-D coordinates and explicit hydrogens.
    output_path : Path
        Where to write the PDBQT.

    Returns
    -------
    str
        The PDBQT string that was written to disk.

    Raises
    ------
    ValueError
        If Meeko preparation or PDBQT writing fails.
    """
    from meeko import MoleculePreparation, PDBQTWriterLegacy

    preparator = MoleculePreparation()
    mol_setups = preparator.prepare(mol)
    if not mol_setups:
        raise ValueError("Meeko failed to prepare molecule (no setups returned)")

    pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setups[0])
    if not is_ok:
        raise ValueError(f"Meeko PDBQT write failed: {error_msg}")

    output_path.write_text(pdbqt_string, encoding="utf-8")
    return pdbqt_string


def _prepare_via_openbabel(input_path: Path, fmt: str, output_path: Path) -> None:
    """Convert a molecular file to PDBQT using Open Babel (fallback).

    Parameters
    ----------
    input_path : Path
        Input molecular-structure file.
    fmt : str
        File format string for Open Babel (e.g. ``"sdf"``, ``"mol2"``).
    output_path : Path
        Where to write the PDBQT.

    Raises
    ------
    RuntimeError
        If Open Babel fails to read the input.
    """
    from openbabel import pybel

    try:
        mol = next(pybel.readfile(fmt, str(input_path)))
    except StopIteration:
        raise RuntimeError(
            f"Open Babel read zero molecules from {input_path}"
        )

    mol.write("pdbqt", str(output_path), overwrite=True)
    logger.info("Open Babel wrote PDBQT: %s", output_path.name)


# ---------------------------------------------------------------------------
# prepare_ligand
# ---------------------------------------------------------------------------

def prepare_ligand(
    input_path: str,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Prepare a ligand for docking, producing a PDBQT file.

    Input detection:
        - If *input_path* points to an existing file with a recognised
          extension, read it directly.
        - If it does not exist as a file but passes SMILES validation,
          convert it to SDF first via ``_smiles_to_sdf``.

    Preparation order:
        1. **Meeko** (RDKit + Meeko) -- preferred, produces torsion trees.
        2. **Open Babel** -- fallback when Meeko fails.

    Parameters
    ----------
    input_path : str
        File path to a molecular-structure file **or** a SMILES string.
    output_dir : str, optional
        Directory for output files.  Defaults to ``LIGANDS_DIR``.

    Returns
    -------
    dict
        ``{pdbqt_path: str, method: str, message: str}``

    Raises
    ------
    FileNotFoundError
        If *input_path* is neither an existing file nor a valid SMILES.
    ValueError
        If both Meeko and Open Babel fail.
    """
    from rdkit import Chem

    out_dir = ensure_dir(Path(output_dir) if output_dir else LIGANDS_DIR)
    src = Path(input_path)

    is_file: bool = src.is_file()
    is_smiles: bool = False
    smiles_str: str = ""
    fmt: str = ""

    if is_file:
        fmt = detect_file_format(input_path)
        if fmt == "unknown":
            raise ValueError(
                f"Unrecognised file format for {input_path}. "
                f"Supported: .sdf, .mol2, .pdb, .mol, .xyz"
            )
        stem = src.stem
        logger.info("Input file detected: %s (format=%s)", src.name, fmt)
    else:
        # Not a file -- try as SMILES
        if validate_smiles(input_path):
            is_smiles = True
            smiles_str = input_path.strip()
            # Generate a deterministic stem from SMILES
            import hashlib

            smiles_hash = hashlib.md5(smiles_str.encode()).hexdigest()[:8]
            stem = f"ligand_{smiles_hash}"
            fmt = "sdf"
            logger.info("Input interpreted as SMILES: %s", smiles_str[:60])
        else:
            raise FileNotFoundError(
                f"'{input_path}' is neither an existing file nor a valid SMILES string"
            )

    # Resolve SMILES → SDF if needed
    working_file: Path
    if is_smiles:
        sdf_path = out_dir / f"{stem}.sdf"
        working_file = _smiles_to_sdf(smiles_str, sdf_path)
    else:
        working_file = src.resolve()

    pdbqt_path = out_dir / f"{stem}.pdbqt"
    method: str = ""

    # ── Primary: Meeko ──────────────────────────────────────────────────
    try:
        mol = _read_molecule_rdkit(working_file, fmt)
        if mol is None:
            raise ValueError(f"RDKit returned None for {working_file}")

        # Ensure hydrogens
        mol = Chem.AddHs(mol, addCoords=True)

        _prepare_via_meeko(mol, pdbqt_path)
        method = "meeko"
        logger.info("Meeko preparation succeeded: %s", pdbqt_path.name)
    except Exception as exc:
        logger.warning("Meeko failed (%s), falling back to Open Babel", exc)

        # ── Fallback: Open Babel ────────────────────────────────────────
        try:
            _prepare_via_openbabel(working_file, fmt, pdbqt_path)
            method = "openbabel"
        except Exception as ob_exc:
            raise ValueError(
                f"Both Meeko and Open Babel failed for {input_path}.\n"
                f"  Meeko error: {exc}\n"
                f"  Open Babel error: {ob_exc}"
            ) from ob_exc

    message = f"Prepared ligand {stem} via {method}: {pdbqt_path.name}"
    logger.info(message)

    return {
        "pdbqt_path": str(pdbqt_path),
        "method": method,
        "message": message,
    }


# ---------------------------------------------------------------------------
# batch_prepare
# ---------------------------------------------------------------------------

def batch_prepare(
    input_dir: str,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Prepare all molecular files in a directory for docking.

    Scans *input_dir* for ``.sdf``, ``.mol2``, and ``.pdb`` files and
    runs :func:`prepare_ligand` on each.

    Parameters
    ----------
    input_dir : str
        Directory containing molecular-structure files.
    output_dir : str, optional
        Directory for output PDBQT files.  Defaults to ``LIGANDS_DIR``.

    Returns
    -------
    dict
        ``{prepared: [str], failed: [{name: str, error: str}], message: str}``
    """
    in_dir = Path(input_dir).resolve()
    if not in_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    out_dir_str: str | None = output_dir

    # Gather eligible files
    eligible: list[Path] = sorted(
        p
        for p in in_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _STRUCTURE_EXTENSIONS
    )

    total = len(eligible)
    logger.info("Found %d eligible files in %s", total, in_dir)

    prepared: list[str] = []
    failed: list[dict[str, str]] = []

    for idx, fpath in enumerate(eligible, 1):
        logger.info("[%d/%d] Preparing %s ...", idx, total, fpath.name)
        try:
            result = prepare_ligand(str(fpath), output_dir=out_dir_str)
            prepared.append(result["pdbqt_path"])
        except Exception as exc:
            logger.error("Failed %s: %s", fpath.name, exc)
            failed.append({"name": fpath.name, "error": str(exc)})

    message = (
        f"Batch preparation complete: {len(prepared)} succeeded, "
        f"{len(failed)} failed out of {total} files"
    )
    logger.info(message)

    return {
        "prepared": prepared,
        "failed": failed,
        "message": message,
    }


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    aspirin_smiles = "CC(=O)Oc1ccccc1C(=O)O"

    print("=== Ligand Preparation Demo: Aspirin from SMILES ===")
    print(f"SMILES: {aspirin_smiles}\n")

    result = prepare_ligand(aspirin_smiles)
    print(json.dumps(result, indent=2))

    # Show the first 20 lines of the PDBQT if it exists
    pdbqt = Path(result["pdbqt_path"])
    if pdbqt.is_file():
        print(f"\n=== First 20 lines of {pdbqt.name} ===")
        lines = pdbqt.read_text(encoding="utf-8").splitlines()
        for line in lines[:20]:
            print(line)
        if len(lines) > 20:
            print(f"... ({len(lines) - 20} more lines)")
