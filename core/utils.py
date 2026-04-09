"""
MoleCopilot utility functions.

Provides shared constants, logging setup, file format detection,
SMILES validation, PDBQT-to-PDB conversion, and protein-ligand merging.
"""

from pathlib import Path
import logging
import sys
import os
import re
from typing import Optional

# ── Project directory constants ──────────────────────────────────────────────

MOLECOPILOT_DIR: Path = Path(__file__).parent.parent
DATA_DIR: Path = MOLECOPILOT_DIR / "data"
PROTEINS_DIR: Path = DATA_DIR / "proteins"
LIGANDS_DIR: Path = DATA_DIR / "ligands"
RESULTS_DIR: Path = DATA_DIR / "results"
LIBRARIES_DIR: Path = DATA_DIR / "libraries"
REPORTS_DIR: Path = MOLECOPILOT_DIR / "reports"

# ── Extension-to-format map ─────────────────────────────────────────────────

_FORMAT_MAP: dict[str, str] = {
    ".pdb": "pdb",
    ".pdbqt": "pdbqt",
    ".sdf": "sdf",
    ".mol2": "mol2",
    ".mol": "sdf",
    ".xyz": "xyz",
    ".cif": "cif",
    ".mmcif": "cif",
}


# ── Public functions ─────────────────────────────────────────────────────────


def validate_smiles(smiles: str) -> bool:
    """Check whether *smiles* encodes a valid molecule using RDKit.

    Parameters
    ----------
    smiles : str
        A SMILES string to validate.

    Returns
    -------
    bool
        ``True`` when RDKit can parse the string into a molecule object,
        ``False`` otherwise (including empty / whitespace-only input).
    """
    if not smiles or not smiles.strip():
        return False
    from rdkit import Chem  # lazy import

    mol = Chem.MolFromSmiles(smiles.strip())
    return mol is not None


def detect_file_format(path: str) -> str:
    """Return the molecular-file format implied by *path*'s extension.

    Parameters
    ----------
    path : str
        Filesystem path (need not exist).

    Returns
    -------
    str
        One of ``"pdb"``, ``"pdbqt"``, ``"sdf"``, ``"mol2"``, ``"xyz"``,
        ``"cif"``, or ``"unknown"`` when the suffix is not recognised.
    """
    ext = Path(path).suffix.lower()
    return _FORMAT_MAP.get(ext, "unknown")


def ensure_dir(path: Path) -> Path:
    """Create *path* (and parents) if it does not already exist.

    Parameters
    ----------
    path : Path
        Directory to create.

    Returns
    -------
    Path
        The same *path*, guaranteed to exist on disk.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(name: str) -> logging.Logger:
    """Return a logger that writes to *stderr* with a MoleCopilot prefix.

    The format is ``[MoleCopilot:{name}] {LEVEL}: {message}``.

    Parameters
    ----------
    name : str
        Short label inserted into the prefix (e.g. ``"fetch_pdb"``).

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    logger = logging.getLogger(f"molecopilot.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        fmt = f"[MoleCopilot:{name}] %(levelname)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger


def load_env() -> dict[str, str]:
    """Read ``~/molecopilot/.env`` and return its key/value pairs.

    Lines that are blank, start with ``#``, or lack an ``=`` are skipped.
    Values are stripped of surrounding quotes (single or double).

    Returns
    -------
    dict[str, str]
        Environment variable mapping.  Empty dict when the file is absent.
    """
    env_path = MOLECOPILOT_DIR / ".env"
    result: dict[str, str] = {}
    if not env_path.is_file():
        return result
    with env_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            result[key] = value
    return result


def pdbqt_to_pdb(pdbqt_path: str, output_path: Optional[str] = None) -> str:
    """Convert a PDBQT file to PDB using Open Babel.

    Parameters
    ----------
    pdbqt_path : str
        Path to the input ``.pdbqt`` file.
    output_path : str, optional
        Desired output path.  Defaults to the same stem with a ``.pdb``
        extension placed in ``LIGANDS_DIR``.

    Returns
    -------
    str
        Absolute path of the written PDB file.

    Raises
    ------
    FileNotFoundError
        If *pdbqt_path* does not exist.
    RuntimeError
        If Open Babel fails to read the input.
    """
    from openbabel import pybel  # lazy import

    src = Path(pdbqt_path)
    if not src.is_file():
        raise FileNotFoundError(f"PDBQT file not found: {pdbqt_path}")

    if output_path is None:
        ensure_dir(LIGANDS_DIR)
        dest = LIGANDS_DIR / (src.stem + ".pdb")
    else:
        dest = Path(output_path)
        ensure_dir(dest.parent)

    logger = setup_logging("utils")

    # Read the first molecule from the PDBQT
    molecules = list(pybel.readfile("pdbqt", str(src)))
    if not molecules:
        raise RuntimeError(f"Open Babel read zero molecules from {pdbqt_path}")

    mol = molecules[0]
    mol.write("pdb", str(dest), overwrite=True)
    logger.info("Converted PDBQT → PDB: %s", str(dest))
    return str(dest.resolve())


def merge_protein_ligand(
    protein_pdb: str,
    ligand_pdb: str,
    output_path: Optional[str] = None,
) -> str:
    """Merge a protein PDB and a ligand PDB into one file for PLIP analysis.

    **Critical behaviour**: every ``ATOM`` record that originates from the
    ligand file is rewritten as ``HETATM`` so that PLIP (and other tools)
    correctly identify the ligand as a hetero-group.  The residue name
    present in the ligand file is preserved (commonly ``UNL``).

    Parameters
    ----------
    protein_pdb : str
        Path to the protein PDB file.
    ligand_pdb : str
        Path to the ligand PDB file.
    output_path : str, optional
        Where to write the merged file.  Defaults to
        ``RESULTS_DIR / "complex.pdb"``.

    Returns
    -------
    str
        Absolute path of the merged PDB file.

    Raises
    ------
    FileNotFoundError
        If either input file is missing.
    """
    protein_path = Path(protein_pdb)
    ligand_path = Path(ligand_pdb)
    if not protein_path.is_file():
        raise FileNotFoundError(f"Protein PDB not found: {protein_pdb}")
    if not ligand_path.is_file():
        raise FileNotFoundError(f"Ligand PDB not found: {ligand_pdb}")

    if output_path is None:
        ensure_dir(RESULTS_DIR)
        dest = RESULTS_DIR / "complex.pdb"
    else:
        dest = Path(output_path)
        ensure_dir(dest.parent)

    logger = setup_logging("utils")

    protein_lines: list[str] = []
    ligand_lines: list[str] = []

    # ── Read protein ────────────────────────────────────────────────────
    with protein_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            record = line[:6].strip()
            if record in ("ATOM", "HETATM", "TER", "MODEL", "ENDMDL"):
                protein_lines.append(line.rstrip("\n"))

    # ── Read ligand, converting ATOM → HETATM ──────────────────────────
    converted = 0
    with ligand_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            record = line[:6].strip()
            if record == "ATOM":
                # PDB fixed-width: columns 1-6 are the record type.
                # "ATOM  " → "HETATM"  (both 6 chars)
                new_line = "HETATM" + line[6:]
                ligand_lines.append(new_line.rstrip("\n"))
                converted += 1
            elif record in ("HETATM", "TER"):
                ligand_lines.append(line.rstrip("\n"))

    if converted:
        logger.info(
            "Converted %d ligand ATOM records to HETATM", converted
        )

    # ── Write merged file ───────────────────────────────────────────────
    with dest.open("w", encoding="utf-8") as fh:
        for pline in protein_lines:
            fh.write(pline + "\n")
        # Separate protein and ligand with TER if not already present
        if protein_lines and not protein_lines[-1].startswith("TER"):
            fh.write("TER\n")
        for lline in ligand_lines:
            fh.write(lline + "\n")
        fh.write("END\n")

    logger.info("Merged complex written to %s", str(dest))
    return str(dest.resolve())


# ── Standalone demo ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    log = setup_logging("utils-demo")

    # Directory constants
    print("=== MoleCopilot Directory Layout ===")
    for label, d in [
        ("Root", MOLECOPILOT_DIR),
        ("Data", DATA_DIR),
        ("Proteins", PROTEINS_DIR),
        ("Ligands", LIGANDS_DIR),
        ("Results", RESULTS_DIR),
        ("Libraries", LIBRARIES_DIR),
        ("Reports", REPORTS_DIR),
    ]:
        exists = d.is_dir()
        print(f"  {label:10s} {d}  {'[exists]' if exists else '[missing]'}")

    # SMILES validation
    print("\n=== SMILES Validation ===")
    test_smiles = [
        ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
        ("Caffeine", "Cn1c(=O)c2c(ncn2C)n(C)c1=O"),
        ("Invalid", "not_a_smiles_XYZ"),
        ("Empty", ""),
    ]
    for name, smi in test_smiles:
        valid = validate_smiles(smi)
        print(f"  {name:12s} {smi[:40]:40s} → {'VALID' if valid else 'INVALID'}")

    # File format detection
    print("\n=== File Format Detection ===")
    test_paths = [
        "protein.pdb",
        "ligand.pdbqt",
        "compound.sdf",
        "molecule.mol2",
        "readme.txt",
    ]
    for tp in test_paths:
        fmt = detect_file_format(tp)
        print(f"  {tp:24s} → {fmt}")

    # Env loading
    print("\n=== Environment (.env) ===")
    env = load_env()
    if env:
        for k, v in env.items():
            print(f"  {k} = {v}")
    else:
        print("  (no .env found or file is empty)")

    log.info("Demo complete.")
