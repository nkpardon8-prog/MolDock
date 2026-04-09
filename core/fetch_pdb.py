"""
MoleCopilot — Protein Data Bank (RCSB) fetch & search utilities.

Download PDB files, query the RCSB search API, and retrieve
structured metadata for any PDB entry.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from core.utils import (
    PROTEINS_DIR,
    ensure_dir,
    setup_logging,
)

_logger = setup_logging("fetch_pdb")


# ── Public functions ─────────────────────────────────────────────────────────


def fetch_protein(
    pdb_id: str,
    output_dir: Optional[str] = None,
) -> dict[str, str]:
    """Download a PDB file from RCSB and save it locally.

    The download is retried up to 3 times with exponential back-off
    (1 s, 2 s, 4 s).  The response is validated to contain at least one
    ``ATOM`` or ``HEADER`` record.

    Parameters
    ----------
    pdb_id : str
        Four-character PDB identifier (case-insensitive).
    output_dir : str, optional
        Directory in which to save the file.  Defaults to
        ``PROTEINS_DIR``.

    Returns
    -------
    dict
        ``{"file_path": str, "pdb_id": str, "message": str}``

    Raises
    ------
    RuntimeError
        If the download fails after all retries or if the response is not
        a valid PDB file.
    """
    import requests  # lazy

    pdb_id = pdb_id.strip().upper()
    if len(pdb_id) != 4:
        raise ValueError(f"PDB ID must be exactly 4 characters, got: {pdb_id!r}")

    dest_dir = Path(output_dir) if output_dir else PROTEINS_DIR
    ensure_dir(dest_dir)
    dest_file = dest_dir / f"{pdb_id}.pdb"

    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"

    max_retries = 3
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            _logger.info(
                "Downloading %s (attempt %d/%d)…", pdb_id, attempt, max_retries
            )
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()

            text = resp.text
            # Basic validation: look for ATOM or HEADER records
            has_atom = any(
                line.startswith(("ATOM", "HETATM")) for line in text.splitlines()
            )
            has_header = any(
                line.startswith("HEADER") for line in text.splitlines()
            )
            if not (has_atom or has_header):
                raise RuntimeError(
                    f"Response for {pdb_id} does not look like a valid PDB file"
                )

            dest_file.write_text(text, encoding="utf-8")
            _logger.info("Saved %s → %s", pdb_id, str(dest_file))
            return {
                "file_path": str(dest_file.resolve()),
                "pdb_id": pdb_id,
                "message": f"Successfully downloaded {pdb_id}",
            }

        except Exception as exc:
            last_error = exc
            _logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt < max_retries:
                backoff = 2 ** (attempt - 1)  # 1, 2, 4 seconds
                time.sleep(backoff)

    raise RuntimeError(
        f"Failed to download {pdb_id} after {max_retries} attempts: {last_error}"
    )


def search_pdb(
    query: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Full-text search against the RCSB PDB search API (v2).

    After obtaining matching PDB IDs the function fetches per-entry
    metadata (title, resolution, method, organism) via the RCSB data API.

    Parameters
    ----------
    query : str
        Free-text search term (e.g. ``"kinase"``).
    max_results : int
        Maximum number of results to return (default 10).

    Returns
    -------
    list[dict]
        Each dict contains ``pdb_id``, ``title``, ``resolution``,
        ``method``, and ``organism``.
    """
    import requests  # lazy

    search_url = "https://search.rcsb.org/rcsbsearch/v2/query"

    payload: dict[str, Any] = {
        "query": {
            "type": "terminal",
            "service": "full_text",
            "parameters": {"value": query},
        },
        "return_type": "entry",
        "request_options": {
            "paginate": {"start": 0, "rows": max_results},
            "results_content_type": ["experimental"],
        },
    }

    _logger.info("Searching RCSB for %r (max %d)…", query, max_results)
    resp = requests.post(search_url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    result_set = data.get("result_set", [])
    if not result_set:
        _logger.info("No results found for %r", query)
        return []

    pdb_ids: list[str] = [entry["identifier"] for entry in result_set]

    results: list[dict[str, Any]] = []
    for pid in pdb_ids:
        info = _fetch_entry_metadata(pid)
        results.append(info)
        time.sleep(0.1)  # polite rate-limiting

    _logger.info("Returned %d results for %r", len(results), query)
    return results


def get_protein_info(pdb_id: str) -> dict[str, Any]:
    """Fetch rich metadata for a single PDB entry from the RCSB data API.

    Parameters
    ----------
    pdb_id : str
        Four-character PDB identifier.

    Returns
    -------
    dict
        Keys: ``title``, ``organism``, ``resolution``, ``method``,
        ``chains``, ``ligands``, ``citation``.
    """
    import requests  # lazy

    pdb_id = pdb_id.strip().upper()
    url = f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}"

    _logger.info("Fetching metadata for %s…", pdb_id)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()

    # ── Title ────────────────────────────────────────────────────────────
    title: str = data.get("struct", {}).get("title", "N/A")

    # ── Experimental method & resolution ─────────────────────────────────
    method: str = "N/A"
    resolution: float | None = None
    exptl = data.get("exptl", [])
    if exptl:
        method = exptl[0].get("method", "N/A")
    refine = data.get("refine", [])
    if refine:
        resolution = refine[0].get("ls_d_res_high")
    # Fallback: rcsb_entry_info
    if resolution is None:
        resolution = (
            data.get("rcsb_entry_info", {}).get("resolution_combined", [None])[0]
        )

    # ── Organism (source) ────────────────────────────────────────────────
    organism: str = "N/A"
    entity_src = data.get("rcsb_entry_container_identifiers", {}).get(
        "polymer_entity_ids", []
    )
    # Try the struct_keywords or polymer entities for source organism
    polymer_entities = data.get("polymer_entities", [])
    if polymer_entities:
        src_list = polymer_entities[0].get("rcsb_entity_source_organism", [])
        if src_list:
            organism = src_list[0].get("ncbi_scientific_name", "N/A")
    # Fallback via separate call
    if organism == "N/A":
        organism = _fetch_organism(pdb_id)

    # ── Chains ───────────────────────────────────────────────────────────
    chains: list[str] = (
        data.get("rcsb_entry_container_identifiers", {}).get("auth_asym_ids", [])
    )

    # ── Ligands (non-polymer entity IDs) ─────────────────────────────────
    ligands: list[str] = (
        data.get("rcsb_entry_container_identifiers", {}).get(
            "non_polymer_entity_ids", []
        )
    )
    # Try to resolve ligand component IDs
    ligand_ids: list[str] = _fetch_ligand_ids(pdb_id)
    if ligand_ids:
        ligands = ligand_ids

    # ── Citation ─────────────────────────────────────────────────────────
    citation: dict[str, str] = {}
    cit = data.get("citation", [])
    if cit:
        primary = cit[0]
        citation = {
            "title": primary.get("title", "N/A"),
            "journal": primary.get("journal_abbrev", "N/A"),
            "year": str(primary.get("year", "N/A")),
            "doi": primary.get("pdbx_database_id_DOI", "N/A"),
        }

    result: dict[str, Any] = {
        "pdb_id": pdb_id,
        "title": title,
        "organism": organism,
        "resolution": resolution,
        "method": method,
        "chains": chains,
        "ligands": ligands,
        "citation": citation,
    }
    _logger.info("Metadata retrieved for %s", pdb_id)
    return result


# ── Private helpers ──────────────────────────────────────────────────────────


def _fetch_entry_metadata(pdb_id: str) -> dict[str, Any]:
    """Lightweight metadata fetch used by :func:`search_pdb`."""
    import requests  # lazy

    url = f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {
            "pdb_id": pdb_id,
            "title": "N/A",
            "resolution": None,
            "method": "N/A",
            "organism": "N/A",
        }

    title = data.get("struct", {}).get("title", "N/A")
    method = "N/A"
    exptl = data.get("exptl", [])
    if exptl:
        method = exptl[0].get("method", "N/A")
    resolution = None
    refine = data.get("refine", [])
    if refine:
        resolution = refine[0].get("ls_d_res_high")
    if resolution is None:
        resolution = (
            data.get("rcsb_entry_info", {}).get("resolution_combined", [None])[0]
        )

    organism = "N/A"
    polymer_entities = data.get("polymer_entities", [])
    if polymer_entities:
        src_list = polymer_entities[0].get("rcsb_entity_source_organism", [])
        if src_list:
            organism = src_list[0].get("ncbi_scientific_name", "N/A")
    if organism == "N/A":
        organism = _fetch_organism(pdb_id)

    return {
        "pdb_id": pdb_id,
        "title": title,
        "resolution": resolution,
        "method": method,
        "organism": organism,
    }


def _fetch_organism(pdb_id: str) -> str:
    """Best-effort organism lookup via the polymer entity endpoint."""
    import requests  # lazy

    url = f"https://data.rcsb.org/rest/v1/core/polymer_entity/{pdb_id}/1"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        src = data.get("rcsb_entity_source_organism", [])
        if src:
            return src[0].get("ncbi_scientific_name", "N/A")
    except Exception:
        pass
    return "N/A"


def _fetch_ligand_ids(pdb_id: str) -> list[str]:
    """Return chemical component IDs for non-polymer entities (ligands)."""
    import requests  # lazy

    url = f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        np_ids = (
            data.get("rcsb_entry_container_identifiers", {}).get(
                "non_polymer_entity_ids", []
            )
        )
        comp_ids: list[str] = []
        for eid in np_ids:
            ent_url = (
                f"https://data.rcsb.org/rest/v1/core/nonpolymer_entity/{pdb_id}/{eid}"
            )
            ent_resp = requests.get(ent_url, timeout=10)
            if ent_resp.ok:
                ent_data = ent_resp.json()
                comp_id = ent_data.get("pdbx_entity_nonpoly", {}).get("comp_id")
                if comp_id:
                    comp_ids.append(comp_id)
        return comp_ids
    except Exception:
        return []


# ── Standalone demo ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_pdb = "3S7S"

    print(f"=== Fetching protein {demo_pdb} ===")
    result = fetch_protein(demo_pdb)
    print(json.dumps(result, indent=2))

    print(f"\n=== Protein info for {demo_pdb} ===")
    info = get_protein_info(demo_pdb)
    print(json.dumps(info, indent=2, default=str))

    print(f"\n=== Searching RCSB for 'kinase' (top 3) ===")
    hits = search_pdb("kinase", max_results=3)
    for h in hits:
        print(json.dumps(h, indent=2, default=str))
