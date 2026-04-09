"""
ADMET property checking for MoleCopilot.

Provides Lipinski Rule-of-Five, Veber oral bioavailability, and combined
drug-likeness scoring using RDKit molecular descriptors.
"""

from pathlib import Path
from typing import Optional

from core.utils import setup_logging, RESULTS_DIR, REPORTS_DIR, ensure_dir

import importlib.util as _importlib_util
import os as _os
from rdkit.Chem import RDConfig as _RDConfig

_sa_spec = _importlib_util.spec_from_file_location(
    "sascorer", _os.path.join(_RDConfig.RDContribDir, "SA_Score", "sascorer.py"))
_sascorer = _importlib_util.module_from_spec(_sa_spec)
_sa_spec.loader.exec_module(_sascorer)

logger = setup_logging("admet_check")


# ── Public functions ─────────────────────────────────────────────────────────


def calculate_sa_score(smiles: str) -> dict:
    """Calculate the Synthetic Accessibility (SA) Score for a molecule.

    The SA Score ranges from 1 (easy to synthesize) to 10 (very difficult).
    It is based on fragment contributions and molecular complexity as
    described by Ertl & Schuffenhauer (2009).

    Parameters
    ----------
    smiles : str
        SMILES representation of the molecule.

    Returns
    -------
    dict
        Keys: sa_score (float), synthetic_assessment (str).
    """
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"sa_score": 10.0, "synthetic_assessment": "Very Difficult"}

    sa: float = round(_sascorer.calculateScore(mol), 2)

    if sa <= 3:
        assessment = "Easy"
    elif sa <= 5:
        assessment = "Moderate"
    elif sa <= 7:
        assessment = "Difficult"
    else:
        assessment = "Very Difficult"

    return {"sa_score": sa, "synthetic_assessment": assessment}


def check_lipinski(smiles: str) -> dict:
    """Evaluate Lipinski's Rule of Five for a SMILES string.

    The rule states that an orally active drug generally has no more than
    one violation of the following: MW <= 500, LogP <= 5, HBD <= 5,
    HBA <= 10.

    Parameters
    ----------
    smiles : str
        SMILES representation of the molecule.

    Returns
    -------
    dict
        Keys: passes (bool), mw (float), logp (float), hbd (int),
        hba (int), violations (int), details (str).
    """
    from rdkit import Chem
    from rdkit.Chem import Descriptors

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.error("Invalid SMILES for Lipinski check: %s", smiles)
        return {
            "passes": False,
            "mw": 0.0,
            "logp": 0.0,
            "hbd": 0,
            "hba": 0,
            "violations": 4,
            "details": "Invalid SMILES string",
        }

    mw: float = round(Descriptors.MolWt(mol), 2)
    logp: float = round(Descriptors.MolLogP(mol), 2)
    hbd: int = int(Descriptors.NumHDonors(mol))
    hba: int = int(Descriptors.NumHAcceptors(mol))

    violations: int = 0
    violation_details: list[str] = []

    if mw > 500:
        violations += 1
        violation_details.append(f"MW {mw} > 500")
    if logp > 5:
        violations += 1
        violation_details.append(f"LogP {logp} > 5")
    if hbd > 5:
        violations += 1
        violation_details.append(f"HBD {hbd} > 5")
    if hba > 10:
        violations += 1
        violation_details.append(f"HBA {hba} > 10")

    passes: bool = violations <= 1
    details: str = (
        "All rules satisfied"
        if violations == 0
        else "; ".join(violation_details)
    )

    return {
        "passes": passes,
        "mw": mw,
        "logp": logp,
        "hbd": hbd,
        "hba": hba,
        "violations": violations,
        "details": details,
    }


def check_veber(smiles: str) -> dict:
    """Evaluate Veber's oral bioavailability rules for a SMILES string.

    Veber criteria: rotatable bonds <= 10 and TPSA <= 140 A^2.

    Parameters
    ----------
    smiles : str
        SMILES representation of the molecule.

    Returns
    -------
    dict
        Keys: passes (bool), rotatable_bonds (int), tpsa (float),
        violations (int).
    """
    from rdkit import Chem
    from rdkit.Chem import Descriptors

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.error("Invalid SMILES for Veber check: %s", smiles)
        return {
            "passes": False,
            "rotatable_bonds": 0,
            "tpsa": 0.0,
            "violations": 2,
        }

    rotatable_bonds: int = int(Descriptors.NumRotatableBonds(mol))
    tpsa: float = round(Descriptors.TPSA(mol), 2)

    violations: int = 0
    if rotatable_bonds > 10:
        violations += 1
    if tpsa > 140:
        violations += 1

    passes: bool = violations == 0

    return {
        "passes": passes,
        "rotatable_bonds": rotatable_bonds,
        "tpsa": tpsa,
        "violations": violations,
    }


def full_admet(smiles: str) -> dict:
    """Run a comprehensive ADMET property check on a SMILES string.

    Combines Lipinski Rule-of-Five, Veber oral bioavailability, and
    additional molecular descriptors into a single drug-likeness
    assessment with a score from 0.0 to 1.0.

    Scoring breakdown:
        - Lipinski all pass (0 violations): +0.4
        - Veber all pass (0 violations): +0.2
        - MW in 200-450 range: +0.1
        - LogP in 1-3 range: +0.1
        - TPSA in 40-90 range: +0.1
        - fraction_csp3 > 0.25: +0.1

    Assessment thresholds:
        >= 0.8  "Excellent"
        >= 0.6  "Good"
        >= 0.4  "Moderate"
        <  0.4  "Poor"

    Parameters
    ----------
    smiles : str
        SMILES representation of the molecule.

    Returns
    -------
    dict
        Full property dict with all descriptors, scores, and assessment.
    """
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.error("Invalid SMILES for full ADMET: %s", smiles)
        return {
            "smiles": smiles,
            "valid": False,
            "lipinski": check_lipinski(smiles),
            "veber": check_veber(smiles),
            "drug_likeness_score": 0.0,
            "assessment": "Poor",
            "sa_score": 10.0,
            "synthetic_assessment": "Very Difficult",
            "details": "Invalid SMILES string",
        }

    lipinski: dict = check_lipinski(smiles)
    veber: dict = check_veber(smiles)

    # Additional descriptors
    num_rings: int = int(rdMolDescriptors.CalcNumRings(mol))
    num_aromatic_rings: int = int(rdMolDescriptors.CalcNumAromaticRings(mol))
    fraction_csp3: float = round(rdMolDescriptors.CalcFractionCSP3(mol), 3)
    molar_refractivity: float = round(Descriptors.MolMR(mol), 2)
    num_heavy_atoms: int = int(mol.GetNumHeavyAtoms())

    sa_result: dict = calculate_sa_score(smiles)

    # Drug-likeness score computation
    score: float = 0.0

    if lipinski["violations"] == 0:
        score += 0.4
    if veber["violations"] == 0:
        score += 0.2
    if 200 <= lipinski["mw"] <= 450:
        score += 0.1
    if 1 <= lipinski["logp"] <= 3:
        score += 0.1
    if 40 <= veber["tpsa"] <= 90:
        score += 0.1
    if fraction_csp3 > 0.25:
        score += 0.1

    score = round(score, 2)

    if score >= 0.8:
        assessment = "Excellent"
    elif score >= 0.6:
        assessment = "Good"
    elif score >= 0.4:
        assessment = "Moderate"
    else:
        assessment = "Poor"

    return {
        "smiles": smiles,
        "valid": True,
        "lipinski": lipinski,
        "veber": veber,
        "mw": lipinski["mw"],
        "logp": lipinski["logp"],
        "hbd": lipinski["hbd"],
        "hba": lipinski["hba"],
        "rotatable_bonds": veber["rotatable_bonds"],
        "tpsa": veber["tpsa"],
        "num_rings": num_rings,
        "num_aromatic_rings": num_aromatic_rings,
        "fraction_csp3": fraction_csp3,
        "molar_refractivity": molar_refractivity,
        "num_heavy_atoms": num_heavy_atoms,
        "sa_score": sa_result["sa_score"],
        "synthetic_assessment": sa_result["synthetic_assessment"],
        "drug_likeness_score": score,
        "assessment": assessment,
    }


def batch_admet(
    smiles_list: list[str],
    names: Optional[list[str]] = None,
) -> dict:
    """Run full_admet on a list of SMILES and save results to CSV.

    Parameters
    ----------
    smiles_list : list[str]
        List of SMILES strings.
    names : list[str], optional
        Compound names corresponding to each SMILES. Defaults to
        "Compound_1", "Compound_2", etc.

    Returns
    -------
    dict
        Keys: csv_path (str), results (list[dict]), summary (str).
    """
    import csv

    if names is None:
        names = [f"Compound_{i + 1}" for i in range(len(smiles_list))]

    if len(names) != len(smiles_list):
        logger.warning(
            "Names list length (%d) != SMILES list length (%d); padding",
            len(names),
            len(smiles_list),
        )
        while len(names) < len(smiles_list):
            names.append(f"Compound_{len(names) + 1}")
        names = names[: len(smiles_list)]

    results: list[dict] = []
    for i, smi in enumerate(smiles_list):
        logger.info("Checking ADMET for %s: %s", names[i], smi)
        result: dict = full_admet(smi)
        result["name"] = names[i]
        results.append(result)

    # Save to CSV
    csv_dir: Path = ensure_dir(RESULTS_DIR)
    csv_path: Path = csv_dir / "admet_results.csv"

    fieldnames: list[str] = [
        "name",
        "smiles",
        "valid",
        "mw",
        "logp",
        "hbd",
        "hba",
        "rotatable_bonds",
        "tpsa",
        "num_rings",
        "num_aromatic_rings",
        "fraction_csp3",
        "molar_refractivity",
        "num_heavy_atoms",
        "drug_likeness_score",
        "sa_score",
        "synthetic_assessment",
        "assessment",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    logger.info("ADMET results saved to %s", str(csv_path))

    # Build summary
    excellent: int = sum(1 for r in results if r["assessment"] == "Excellent")
    good: int = sum(1 for r in results if r["assessment"] == "Good")
    moderate: int = sum(1 for r in results if r["assessment"] == "Moderate")
    poor: int = sum(1 for r in results if r["assessment"] == "Poor")
    total: int = len(results)

    summary: str = (
        f"ADMET batch analysis complete: {total} compounds. "
        f"Excellent: {excellent}, Good: {good}, "
        f"Moderate: {moderate}, Poor: {poor}."
    )

    return {
        "csv_path": str(csv_path),
        "results": results,
        "summary": summary,
    }


# ── Standalone demo ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("MoleCopilot ADMET Check — Demo")
    print("=" * 60)

    demo_compounds: list[tuple[str, str]] = [
        ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
        ("Caffeine", "Cn1c(=O)c2c(ncn2C)n(C)c1=O"),
        ("Exemestane", "CC12CCC3C(C1CCC2=O)CC(=C)C4=CC(=O)C=CC34C"),
    ]

    # Individual checks
    for name, smi in demo_compounds:
        print(f"\n--- {name} ({smi}) ---")

        lip = check_lipinski(smi)
        print(f"  Lipinski: passes={lip['passes']}, "
              f"MW={lip['mw']}, LogP={lip['logp']}, "
              f"HBD={lip['hbd']}, HBA={lip['hba']}, "
              f"violations={lip['violations']}")
        print(f"    Details: {lip['details']}")

        veb = check_veber(smi)
        print(f"  Veber: passes={veb['passes']}, "
              f"RotBonds={veb['rotatable_bonds']}, "
              f"TPSA={veb['tpsa']}, "
              f"violations={veb['violations']}")

        full = full_admet(smi)
        print(f"  Drug-likeness score: {full['drug_likeness_score']}")
        print(f"  Assessment: {full['assessment']}")
        print(f"  SA Score: {full['sa_score']} ({full['synthetic_assessment']})")
        print(f"  Extra: rings={full['num_rings']}, "
              f"aromatic_rings={full['num_aromatic_rings']}, "
              f"Fsp3={full['fraction_csp3']}, "
              f"MR={full['molar_refractivity']}, "
              f"heavy_atoms={full['num_heavy_atoms']}")

    # Batch check
    print("\n" + "=" * 60)
    print("Batch ADMET")
    print("=" * 60)

    smiles_list = [smi for _, smi in demo_compounds]
    name_list = [name for name, _ in demo_compounds]

    batch_result = batch_admet(smiles_list, name_list)
    print(f"\n  CSV saved to: {batch_result['csv_path']}")
    print(f"  Summary: {batch_result['summary']}")
    for r in batch_result["results"]:
        print(f"    {r['name']}: score={r['drug_likeness_score']} "
              f"({r['assessment']})")

    print("\nDone.")
