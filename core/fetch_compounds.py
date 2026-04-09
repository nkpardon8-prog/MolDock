"""
MoleCopilot — PubChem compound search and SDF generation utilities.

Search PubChem by name, download 3-D SDF structures, and convert
SMILES strings to 3-D SDF files with RDKit.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from core.utils import (
    LIGANDS_DIR,
    ensure_dir,
    setup_logging,
    validate_smiles,
)

_logger = setup_logging("fetch_compounds")

# PubChem PUG-REST base
_PUG_BASE: str = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


# ── Public functions ─────────────────────────────────────────────────────────


def search_pubchem(
    query: str,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Search PubChem by compound name and return property data.

    Uses a two-step PUG-REST approach:

    1. Resolve *query* to CIDs via the ``/compound/name/.../cids`` endpoint.
    2. Batch-fetch properties (SMILES, formula, MW, IUPAC name) for all
       returned CIDs in a single call.

    A 0.25 s sleep is inserted between the two HTTP requests to stay
    within PubChem rate limits.

    Parameters
    ----------
    query : str
        Compound name or synonym (e.g. ``"aspirin"``).
    max_results : int
        Maximum CIDs to request (default 20).

    Returns
    -------
    list[dict]
        Each dict contains ``name``, ``cid``, ``smiles``, ``formula``,
        ``mw`` (float), and ``iupac_name``.
    """
    import requests  # lazy

    query = query.strip()
    if not query:
        raise ValueError("Search query must not be empty")

    # ── Step 1: resolve name → CIDs ─────────────────────────────────────
    cids_url = f"{_PUG_BASE}/compound/name/{query}/cids/JSON"
    _logger.info("Resolving %r → CIDs…", query)
    resp = requests.get(cids_url, timeout=30)
    resp.raise_for_status()
    cid_data = resp.json()

    cids: list[int] = cid_data.get("IdentifierList", {}).get("CID", [])
    if not cids:
        _logger.info("No CIDs found for %r", query)
        return []

    cids = cids[:max_results]
    _logger.info("Found %d CIDs for %r", len(cids), query)

    # ── Rate limit ───────────────────────────────────────────────────────
    time.sleep(0.25)

    # ── Step 2: batch-fetch properties ───────────────────────────────────
    cid_str = ",".join(str(c) for c in cids)
    props = "CanonicalSMILES,MolecularFormula,MolecularWeight,IUPACName"
    props_url = f"{_PUG_BASE}/compound/cid/{cid_str}/property/{props}/JSON"

    _logger.info("Fetching properties for %d CIDs…", len(cids))
    resp = requests.get(props_url, timeout=30)
    resp.raise_for_status()
    props_data = resp.json()

    table = props_data.get("PropertyTable", {}).get("Properties", [])

    results: list[dict[str, Any]] = []
    for row in table:
        results.append(
            {
                "name": query,
                "cid": int(row.get("CID", 0)),
                "smiles": row.get("CanonicalSMILES") or row.get("ConnectivitySMILES", ""),
                "formula": row.get("MolecularFormula", ""),
                "mw": float(row.get("MolecularWeight", 0.0)),
                "iupac_name": row.get("IUPACName", "N/A"),
            }
        )

    _logger.info("Returned %d compound records for %r", len(results), query)
    return results


def fetch_compound_sdf(
    cid: int,
    output_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Download an SDF for *cid* from PubChem, preferring the 3-D conformer.

    If only the 2-D record is available, RDKit is used to generate 3-D
    coordinates (``AllChem.EmbedMolecule`` with ETKDGv3, followed by
    MMFF optimisation).

    Parameters
    ----------
    cid : int
        PubChem compound ID.
    output_dir : str, optional
        Directory for the saved SDF.  Defaults to ``LIGANDS_DIR``.

    Returns
    -------
    dict
        ``{"sdf_path": str, "cid": int, "is_3d": bool, "message": str}``
    """
    import requests  # lazy

    dest_dir = Path(output_dir) if output_dir else LIGANDS_DIR
    ensure_dir(dest_dir)
    dest_file = dest_dir / f"CID_{cid}.sdf"

    # ── Try 3-D first ────────────────────────────────────────────────────
    url_3d = f"{_PUG_BASE}/compound/cid/{cid}/SDF?record_type=3d"
    _logger.info("Trying 3-D SDF for CID %d…", cid)
    resp_3d = requests.get(url_3d, timeout=30)

    if resp_3d.ok and _looks_like_sdf(resp_3d.text):
        dest_file.write_text(resp_3d.text, encoding="utf-8")
        _logger.info("Saved 3-D SDF → %s", str(dest_file))
        return {
            "sdf_path": str(dest_file.resolve()),
            "cid": cid,
            "is_3d": True,
            "message": f"Downloaded 3-D SDF for CID {cid}",
        }

    # ── Fallback to 2-D ─────────────────────────────────────────────────
    time.sleep(0.25)
    url_2d = f"{_PUG_BASE}/compound/cid/{cid}/SDF"
    _logger.info("Falling back to 2-D SDF for CID %d…", cid)
    resp_2d = requests.get(url_2d, timeout=30)
    resp_2d.raise_for_status()

    sdf_text = resp_2d.text
    if not _looks_like_sdf(sdf_text):
        raise RuntimeError(f"PubChem returned invalid SDF for CID {cid}")

    # ── Generate 3-D coords with RDKit ───────────────────────────────────
    _logger.info("Generating 3-D coordinates with RDKit for CID %d…", cid)
    sdf_3d_text = _generate_3d_from_sdf(sdf_text)

    if sdf_3d_text is not None:
        dest_file.write_text(sdf_3d_text, encoding="utf-8")
        _logger.info("Saved RDKit-generated 3-D SDF → %s", str(dest_file))
        return {
            "sdf_path": str(dest_file.resolve()),
            "cid": cid,
            "is_3d": True,
            "message": f"Downloaded 2-D SDF for CID {cid}, generated 3-D with RDKit",
        }

    # If 3-D generation failed, save the 2-D as-is
    dest_file.write_text(sdf_text, encoding="utf-8")
    _logger.warning(
        "Saved 2-D SDF (3-D generation failed) → %s", str(dest_file)
    )
    return {
        "sdf_path": str(dest_file.resolve()),
        "cid": cid,
        "is_3d": False,
        "message": f"Downloaded 2-D SDF for CID {cid} (3-D generation failed)",
    }


def smiles_to_sdf(
    smiles: str,
    name: str,
    output_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Convert a SMILES string to a 3-D SDF file using RDKit.

    Pipeline: ``MolFromSmiles`` → ``AddHs`` → ``EmbedMolecule``
    (ETKDGv3) → ``MMFFOptimizeMolecule`` → ``SDWriter``.

    Parameters
    ----------
    smiles : str
        Valid SMILES string.
    name : str
        Molecule name used as the file stem and the SD ``_Name`` property.
    output_dir : str, optional
        Directory for the written SDF.  Defaults to ``LIGANDS_DIR``.

    Returns
    -------
    dict
        ``{"sdf_path": str, "name": str, "message": str}``

    Raises
    ------
    ValueError
        If *smiles* cannot be parsed by RDKit.
    RuntimeError
        If 3-D embedding fails.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    if not validate_smiles(smiles):
        raise ValueError(f"Invalid SMILES: {smiles!r}")

    dest_dir = Path(output_dir) if output_dir else LIGANDS_DIR
    ensure_dir(dest_dir)

    # Sanitise the file stem (replace problematic characters)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    dest_file = dest_dir / f"{safe_name}.sdf"

    _logger.info("Converting SMILES → 3-D SDF for %r…", name)

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles!r}")

    mol = Chem.AddHs(mol)
    mol.SetProp("_Name", name)

    # 3-D embedding with ETKDGv3
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    status = AllChem.EmbedMolecule(mol, params)
    if status != 0:
        # Retry without the distance-geometry bounds-matrix smoothing
        _logger.warning("ETKDGv3 failed for %r, retrying with useRandomCoords…", name)
        params.useRandomCoords = True
        status = AllChem.EmbedMolecule(mol, params)
        if status != 0:
            raise RuntimeError(
                f"3-D embedding failed for {name!r} (SMILES: {smiles})"
            )

    # MMFF force-field optimisation
    try:
        opt_result = AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
        if opt_result == -1:
            _logger.warning(
                "MMFF not available for %r, trying UFF…", name
            )
            AllChem.UFFOptimizeMolecule(mol, maxIters=2000)
    except Exception as exc:
        _logger.warning("Force-field optimisation failed for %r: %s", name, exc)

    # Write SDF
    writer = Chem.SDWriter(str(dest_file))
    writer.write(mol)
    writer.close()

    _logger.info("Wrote SDF → %s", str(dest_file))
    return {
        "sdf_path": str(dest_file.resolve()),
        "name": name,
        "message": f"Generated 3-D SDF for {name!r}",
    }


# ── Private helpers ──────────────────────────────────────────────────────────


def _looks_like_sdf(text: str) -> bool:
    """Quick heuristic — an SDF should contain ``$$$$`` and ``V2000`` or ``V3000``."""
    return "$$$$" in text and ("V2000" in text or "V3000" in text)


def _generate_3d_from_sdf(sdf_text: str) -> Optional[str]:
    """Read a 2-D SDF string, embed in 3-D with RDKit, return new SDF text."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    import io

    supplier = Chem.SDMolSupplier()
    supplier.SetData(sdf_text)
    mol = next(supplier, None)
    if mol is None:
        _logger.warning("RDKit could not parse the 2-D SDF")
        return None

    try:
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        status = AllChem.EmbedMolecule(mol, params)
        if status != 0:
            params.useRandomCoords = True
            status = AllChem.EmbedMolecule(mol, params)
            if status != 0:
                _logger.warning("3-D embedding failed for downloaded 2-D SDF")
                return None

        AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)

        buf = io.StringIO()
        writer = Chem.SDWriter(buf)
        writer.write(mol)
        writer.close()
        return buf.getvalue()
    except Exception as exc:
        _logger.warning("3-D generation from 2-D SDF failed: %s", exc)
        return None


# ── Standalone demo ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== PubChem Search: 'aspirin' ===")
    results = search_pubchem("aspirin", max_results=5)
    for r in results:
        print(json.dumps(r, indent=2))

    if results:
        cid = results[0]["cid"]
        print(f"\n=== Fetching SDF for CID {cid} ===")
        sdf_result = fetch_compound_sdf(cid)
        print(json.dumps(sdf_result, indent=2))

    print("\n=== SMILES → SDF: aspirin ===")
    smi_result = smiles_to_sdf("CC(=O)Oc1ccccc1C(=O)O", "aspirin")
    print(json.dumps(smi_result, indent=2))
