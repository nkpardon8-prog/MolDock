"""
MoleCopilot — NVIDIA BioNeMo MolMIM API wrapper.

Generate molecular analogs and optimise drug-like properties via the
MolMIM generative chemistry model hosted on NVIDIA's health API.
Supports CMA-ES property optimisation and latent-space sampling.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from core.utils import setup_logging, validate_smiles

_logger = setup_logging("bionemo")

# ── Constants ────────────────────────────────────────────────────────────────

_MOLMIM_BASE_URL: str = "https://health.api.nvidia.com/v1/biology/nvidia/molmim"
_RETRYABLE_CODES: set[int] = {500, 502, 503, 504}


# ── Private helpers ──────────────────────────────────────────────────────────


def _get_api_key() -> str:
    """Load the NVIDIA API key from the project ``.env`` file.

    The key is read from the ``NVIDIA_API_KEY`` environment variable
    after calling ``load_dotenv`` against the project root ``.env``.

    Returns
    -------
    str
        The API key string.

    Raises
    ------
    RuntimeError
        If the key is not set.
    """
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")

    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError(
            "NVIDIA_API_KEY not found. "
            "Sign up at https://build.nvidia.com/ and add the key to your .env file."
        )
    return key


def _molmim_request(
    endpoint: str,
    payload: dict[str, Any],
    timeout: int = 120,
) -> dict[str, Any]:
    """Send a request to the MolMIM API with retry logic.

    Retries up to 3 times with exponential back-off (1 s, 2 s, 4 s) for
    transient server errors (500/502/503/504) and request timeouts.

    Parameters
    ----------
    endpoint : str
        API endpoint name appended to ``_MOLMIM_BASE_URL``
        (e.g. ``"sampling"`` or ``"generate"``).
    payload : dict
        JSON request body.
    timeout : int
        HTTP request timeout in seconds (default 120).

    Returns
    -------
    dict
        Parsed JSON response from the API.

    Raises
    ------
    RuntimeError
        On authentication failure (401), exhausted credits (402), or
        repeated server errors.
    ValueError
        When the API rejects the input (422).
    """
    import requests  # lazy

    api_key = _get_api_key()
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{_MOLMIM_BASE_URL}/{endpoint}"

    max_retries = 3
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            _logger.info(
                "MolMIM %s request (attempt %d/%d)…",
                endpoint,
                attempt,
                max_retries,
            )
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )

            # ── Non-retryable errors ─────────────────────────────────────
            if resp.status_code == 401:
                raise RuntimeError("NVIDIA API key is invalid")
            if resp.status_code == 402:
                raise RuntimeError("NVIDIA API credits exhausted")
            if resp.status_code == 422:
                detail = resp.text[:300]
                raise ValueError(f"MolMIM rejected input: {detail}")

            # ── Retryable server errors ──────────────────────────────────
            if resp.status_code in _RETRYABLE_CODES:
                last_error = RuntimeError(
                    f"MolMIM returned {resp.status_code}: {resp.text[:200]}"
                )
                _logger.warning(
                    "Server error %d on attempt %d", resp.status_code, attempt
                )
                if attempt < max_retries:
                    backoff = 2 ** (attempt - 1)  # 1, 2, 4 seconds
                    time.sleep(backoff)
                continue

            resp.raise_for_status()
            return resp.json()

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_error = exc
            _logger.warning("Timeout/connection error on attempt %d: %s", attempt, exc)
            if attempt < max_retries:
                backoff = 2 ** (attempt - 1)
                time.sleep(backoff)

    raise RuntimeError(
        f"MolMIM {endpoint} failed after {max_retries} attempts: {last_error}"
    )


def _parse_and_deduplicate(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse the MolMIM response and deduplicate molecules by canonical SMILES.

    The ``data["molecules"]`` field is a **JSON string**, not a list.
    Each molecule is validated and canonicalised with RDKit before
    deduplication.

    Parameters
    ----------
    data : dict
        Raw MolMIM API response containing a ``"molecules"`` key whose
        value is a JSON-encoded string.

    Returns
    -------
    list[dict]
        Unique molecules as ``{"smiles": str, "score": float}`` dicts,
        ordered by first occurrence.
    """
    raw_molecules = json.loads(data["molecules"])

    seen: set[str] = set()
    results: list[dict[str, Any]] = []

    for mol_entry in raw_molecules:
        smiles = mol_entry.get("sample", mol_entry.get("smiles", ""))
        score = float(mol_entry.get("score", 0.0))

        # Validate and canonicalise with RDKit
        try:
            from rdkit import Chem

            rd_mol = Chem.MolFromSmiles(smiles)
            if rd_mol is None:
                _logger.warning("Skipping invalid SMILES: %s", smiles)
                continue
            canonical = Chem.MolToSmiles(rd_mol)
        except Exception as exc:
            _logger.warning("RDKit error for %r: %s", smiles, exc)
            continue

        if canonical in seen:
            continue
        seen.add(canonical)
        results.append({"smiles": canonical, "score": score})

    return results


# ── Public functions ─────────────────────────────────────────────────────────


def sample_analogs(
    smiles: str,
    num_molecules: int = 10,
    scaled_radius: float = 0.5,
) -> dict[str, Any]:
    """Sample molecular analogs around a seed molecule in MolMIM latent space.

    The seed SMILES is encoded into the model's latent space and new
    molecules are decoded from nearby points controlled by
    *scaled_radius*.

    Parameters
    ----------
    smiles : str
        Seed SMILES string (must be RDKit-parseable).
    num_molecules : int
        Number of analogs to generate (default 10).
    scaled_radius : float
        Sampling radius in latent space (default 0.5).  Larger values
        produce more diverse but potentially less similar analogs.

    Returns
    -------
    dict
        ``{"analogs": list[dict], "seed": str, "num_generated": int,
        "method": "sampling", "message": str}``

    Raises
    ------
    ValueError
        If *smiles* is not a valid SMILES string.
    RuntimeError
        On API communication failure.
    """
    if not validate_smiles(smiles):
        raise ValueError(f"Invalid SMILES: {smiles!r}")

    # Cloud API only exposes /generate — use algorithm="none" for unguided sampling
    payload: dict[str, Any] = {
        "smi": smiles,
        "algorithm": "none",
        "num_molecules": num_molecules,
        "property_name": "QED",
    }

    _logger.info(
        "Sampling %d analogs for %s (radius=%.2f)…",
        num_molecules,
        smiles,
        scaled_radius,
    )
    data = _molmim_request("generate", payload)
    analogs = _parse_and_deduplicate(data)

    _logger.info("Generated %d unique analogs", len(analogs))
    return {
        "analogs": analogs,
        "seed": smiles,
        "num_generated": len(analogs),
        "method": "sampling",
        "message": f"Generated {len(analogs)} unique analogs via latent-space sampling",
    }


def optimize_molecules(
    smiles: str,
    property_name: str = "QED",
    num_molecules: int = 20,
    min_similarity: float = 0.3,
    iterations: int = 10,
    particles: int = 30,
) -> dict[str, Any]:
    """Optimise a seed molecule for a target property using CMA-ES.

    The NVIDIA MolMIM model explores its latent space with a CMA-ES
    evolutionary strategy, optimising for *property_name* while
    maintaining at least *min_similarity* (Tanimoto) to the seed.

    Parameters
    ----------
    smiles : str
        Seed SMILES string (must be RDKit-parseable).
    property_name : str
        Property to optimise (default ``"QED"``).
    num_molecules : int
        Number of optimised molecules to return (default 20).
    min_similarity : float
        Minimum Tanimoto similarity to the seed (default 0.3).
    iterations : int
        CMA-ES iteration count (default 10).
    particles : int
        CMA-ES population size per iteration (default 30).

    Returns
    -------
    dict
        ``{"analogs": list[dict], "seed": str, "property": str,
        "score_type": str | None, "num_generated": int,
        "method": "CMA-ES", "message": str}``

    Raises
    ------
    ValueError
        If *smiles* is not a valid SMILES string.
    RuntimeError
        On API communication failure.
    """
    if not validate_smiles(smiles):
        raise ValueError(f"Invalid SMILES: {smiles!r}")

    payload: dict[str, Any] = {
        "smi": smiles,
        "algorithm": "CMA-ES",
        "property_name": property_name,
        "num_molecules": num_molecules,
        "min_similarity": min_similarity,
        "iterations": iterations,
        "particles": particles,
    }

    _logger.info(
        "Optimising %s for %s (n=%d, sim>=%.2f, iter=%d, pop=%d)…",
        smiles,
        property_name,
        num_molecules,
        min_similarity,
        iterations,
        particles,
    )
    data = _molmim_request("generate", payload, timeout=300)
    analogs = _parse_and_deduplicate(data)

    _logger.info("Optimisation returned %d unique molecules", len(analogs))
    return {
        "analogs": analogs,
        "seed": smiles,
        "property": property_name,
        "score_type": data.get("score_type"),
        "num_generated": len(analogs),
        "method": "CMA-ES",
        "message": (
            f"CMA-ES optimisation for {property_name} produced "
            f"{len(analogs)} unique molecules"
        ),
    }


# ── Standalone demo ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    aspirin = "CC(=O)Oc1ccccc1C(=O)O"

    print("=== MolMIM CMA-ES Optimisation (QED) ===")
    opt_result = optimize_molecules(aspirin, property_name="QED", num_molecules=5)
    print(f"Seed:  {opt_result['seed']}")
    print(f"Method: {opt_result['method']}")
    print(f"Generated: {opt_result['num_generated']} molecules\n")
    for i, mol in enumerate(opt_result["analogs"], 1):
        print(f"  {i}. {mol['smiles']}  (score: {mol['score']:.4f})")

    print("\n=== MolMIM Latent-Space Sampling ===")
    sample_result = sample_analogs(aspirin, num_molecules=3)
    print(f"Seed:  {sample_result['seed']}")
    print(f"Method: {sample_result['method']}")
    print(f"Generated: {sample_result['num_generated']} molecules\n")
    for i, mol in enumerate(sample_result["analogs"], 1):
        print(f"  {i}. {mol['smiles']}  (score: {mol['score']:.4f})")
