#!/usr/bin/env python3
"""MoleCopilot — Visualization and figure generation.

Generates publication-quality plots for docking results, ADMET profiles,
and molecular structures using matplotlib, seaborn, and RDKit.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Lazy imports for heavy packages
def _get_logger():
    from core.utils import setup_logging
    return setup_logging("figures")

def _get_dirs():
    from core.utils import REPORTS_DIR, ensure_dir
    return REPORTS_DIR, ensure_dir


def plot_binding_energies(results: list[dict], output_path: str | None = None,
                          top_n: int = 20) -> str:
    """Horizontal bar chart of top compounds by binding energy.

    Each result dict should have 'name' or 'ligand_name' and
    'binding_energy' or 'best_energy'.

    Color coding:
        green: < -8.0 kcal/mol (strong binder)
        gold:  -7.0 to -8.0 kcal/mol (moderate)
        red:   > -7.0 kcal/mol (weak)

    Args:
        results: List of docking result dicts.
        output_path: Where to save PNG. Auto-generated if None.
        top_n: Number of top compounds to show.

    Returns:
        Path to saved PNG file.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    log = _get_logger()
    REPORTS_DIR, ensure_dir = _get_dirs()

    # Normalize keys
    data = []
    for r in results:
        name = r.get("name") or r.get("ligand_name", "unknown")
        energy = r.get("binding_energy") or r.get("best_energy", 0.0)
        if energy is not None:
            data.append({"name": name, "energy": float(energy)})

    # Sort and take top N
    data.sort(key=lambda x: x["energy"])
    data = data[:top_n]

    if not data:
        log.warning("No data to plot for binding energies")
        return ""

    names = [d["name"] for d in data]
    energies = [d["energy"] for d in data]
    colors = []
    for e in energies:
        if e < -8.0:
            colors.append("#2ecc71")  # green
        elif e < -7.0:
            colors.append("#f39c12")  # gold
        else:
            colors.append("#e74c3c")  # red

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(10, max(4, len(data) * 0.4)))
    ax.barh(range(len(names)), energies, color=colors, edgecolor="none")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Binding Energy (kcal/mol)", fontsize=11)
    ax.set_title("Top Compounds by Binding Energy", fontsize=13, fontweight="bold")
    ax.axvline(x=-7.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.text(-7.0, len(names) - 0.5, " -7.0 threshold", fontsize=8, color="gray",
            va="top")
    ax.invert_yaxis()
    plt.tight_layout()

    if not output_path:
        output_path = str(ensure_dir(REPORTS_DIR) / "binding_energies.png")
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Binding energy plot saved to {output_path}")
    return output_path


def plot_admet_radar(admet_dict: dict, compound_name: str,
                     output_path: str | None = None) -> str:
    """Spider/radar plot of drug-likeness properties.

    Axes (normalized to 0-1):
        MW: 0-500, LogP: 0-5, HBD: 0-5, HBA: 0-10,
        RotBonds: 0-10, TPSA: 0-140

    Args:
        admet_dict: Output from full_admet().
        compound_name: Name for the plot title.
        output_path: Where to save PNG.

    Returns:
        Path to saved PNG file.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    log = _get_logger()
    REPORTS_DIR, ensure_dir = _get_dirs()

    categories = ["MW", "LogP", "HBD", "HBA", "RotBonds", "TPSA"]
    max_vals = [500, 5, 5, 10, 10, 140]

    raw = [
        admet_dict.get("mw", 0),
        admet_dict.get("logp", 0),
        admet_dict.get("hbd", 0),
        admet_dict.get("hba", 0),
        admet_dict.get("rotatable_bonds", 0),
        admet_dict.get("tpsa", 0),
    ]
    normalized = [min(v / m, 1.0) for v, m in zip(raw, max_vals)]

    # Ideal ranges (normalized)
    ideal = [
        0.5,   # MW ~250
        0.4,   # LogP ~2
        0.4,   # HBD ~2
        0.4,   # HBA ~4
        0.3,   # RotBonds ~3
        0.5,   # TPSA ~70
    ]

    N = len(categories)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    normalized += normalized[:1]
    ideal += ideal[:1]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.fill(angles, ideal, alpha=0.1, color="green", label="Ideal range")
    ax.plot(angles, ideal, color="green", linewidth=1, linestyle="--", alpha=0.5)
    ax.fill(angles, normalized, alpha=0.25, color="steelblue")
    ax.plot(angles, normalized, color="steelblue", linewidth=2, marker="o",
            markersize=5, label=compound_name)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([f"{c}\n({v})" for c, v in zip(categories,
                        [f"{r:.0f}/{m}" for r, m in zip(raw, max_vals)])],
                       fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_title(f"ADMET Radar — {compound_name}", fontsize=13, fontweight="bold",
                 pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)

    if not output_path:
        safe_name = "".join(c if c.isalnum() else "_" for c in compound_name)
        output_path = str(ensure_dir(REPORTS_DIR) / f"admet_radar_{safe_name}.png")
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"ADMET radar plot saved to {output_path}")
    return output_path


def plot_energy_distribution(results: list[dict],
                             output_path: str | None = None) -> str:
    """Histogram of binding energy distribution.

    Args:
        results: List of docking result dicts with 'binding_energy' or 'best_energy'.
        output_path: Where to save PNG.

    Returns:
        Path to saved PNG file.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    log = _get_logger()
    REPORTS_DIR, ensure_dir = _get_dirs()

    energies = []
    for r in results:
        e = r.get("binding_energy") or r.get("best_energy")
        if e is not None:
            energies.append(float(e))

    if not energies:
        log.warning("No energy data for distribution plot")
        return ""

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(energies, bins=min(30, max(5, len(energies) // 3)),
            color="steelblue", edgecolor="white", alpha=0.8)
    ax.axvline(x=-7.0, color="red", linestyle="--", linewidth=1.5, alpha=0.7)
    ax.text(-7.0, ax.get_ylim()[1] * 0.95, " -7.0 threshold", fontsize=9,
            color="red", va="top")
    ax.set_xlabel("Binding Energy (kcal/mol)", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title("Binding Energy Distribution", fontsize=13, fontweight="bold")
    plt.tight_layout()

    if not output_path:
        output_path = str(ensure_dir(REPORTS_DIR) / "energy_distribution.png")
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Energy distribution plot saved to {output_path}")
    return output_path


def draw_molecule_2d(smiles: str, name: str | None = None,
                     output_path: str | None = None) -> str:
    """2D chemical structure depiction using RDKit Draw.

    Args:
        smiles: SMILES string of the molecule.
        name: Optional name (used in filename if output_path not given).
        output_path: Where to save PNG.

    Returns:
        Path to saved PNG file.
    """
    from rdkit import Chem
    from rdkit.Chem import Draw

    log = _get_logger()
    REPORTS_DIR, ensure_dir = _get_dirs()

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")

    img = Draw.MolToImage(mol, size=(400, 300))

    if not output_path:
        safe_name = "".join(c if c.isalnum() else "_" for c in (name or "molecule"))
        output_path = str(ensure_dir(REPORTS_DIR) / f"structure_{safe_name}.png")

    img.save(output_path)
    log.info(f"2D structure saved to {output_path}")
    return output_path


def plot_interaction_heatmap(interactions_data: list,
                             output_path: str | None = None) -> str:
    """Heatmap of protein-ligand interactions across multiple compounds.

    Args:
        interactions_data: List of dicts, each with 'compound_name' and interaction
            lists (hydrogen_bonds, hydrophobic_contacts, etc.). Each interaction
            should have a 'residue' field.
        output_path: Where to save PNG.

    Returns:
        Path to saved PNG file.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns
    import numpy as np

    log = _get_logger()
    REPORTS_DIR, ensure_dir = _get_dirs()

    if not interactions_data:
        log.warning("No interaction data for heatmap")
        return ""

    # Collect all residues and compounds
    all_residues = set()
    compounds = []
    for entry in interactions_data:
        name = entry.get("compound_name", "unknown")
        compounds.append(name)
        for itype in ["hydrogen_bonds", "hydrophobic_contacts", "pi_stacking",
                       "salt_bridges"]:
            for interaction in entry.get(itype, []):
                res = interaction.get("residue", "")
                if res:
                    all_residues.add(res)

    if not all_residues:
        log.warning("No residue data for heatmap")
        return ""

    residues = sorted(all_residues)
    matrix = np.zeros((len(compounds), len(residues)))

    for i, entry in enumerate(interactions_data):
        for itype in ["hydrogen_bonds", "hydrophobic_contacts", "pi_stacking",
                       "salt_bridges"]:
            for interaction in entry.get(itype, []):
                res = interaction.get("residue", "")
                if res in residues:
                    j = residues.index(res)
                    matrix[i, j] += 1

    sns.set_theme(style="white")
    fig, ax = plt.subplots(figsize=(max(8, len(residues) * 0.5),
                                     max(4, len(compounds) * 0.5)))
    sns.heatmap(matrix, xticklabels=residues, yticklabels=compounds,
                cmap="YlOrRd", annot=True, fmt=".0f", ax=ax,
                linewidths=0.5, cbar_kws={"label": "Interaction count"})
    ax.set_title("Protein-Ligand Interaction Heatmap", fontsize=13,
                 fontweight="bold")
    ax.set_xlabel("Residue", fontsize=10)
    ax.set_ylabel("Compound", fontsize=10)
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.tight_layout()

    if not output_path:
        output_path = str(ensure_dir(REPORTS_DIR) / "interaction_heatmap.png")
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Interaction heatmap saved to {output_path}")
    return output_path


if __name__ == "__main__":
    import os
    os.chdir(str(Path(__file__).parent.parent))

    print("Generating sample figures with mock data...\n")

    # Mock docking results
    mock_results = [
        {"name": "Exemestane", "binding_energy": -9.2},
        {"name": "Letrozole", "binding_energy": -8.7},
        {"name": "Anastrozole", "binding_energy": -8.1},
        {"name": "Thymoquinone", "binding_energy": -6.8},
        {"name": "Aspirin", "binding_energy": -5.9},
        {"name": "Caffeine", "binding_energy": -5.4},
        {"name": "Compound_A", "binding_energy": -7.5},
        {"name": "Compound_B", "binding_energy": -7.2},
        {"name": "Compound_C", "binding_energy": -6.1},
        {"name": "Compound_D", "binding_energy": -8.5},
    ]

    # Mock ADMET
    mock_admet = {
        "mw": 296.4, "logp": 2.1, "hbd": 0, "hba": 3,
        "rotatable_bonds": 1, "tpsa": 34.14,
    }

    p1 = plot_binding_energies(mock_results)
    print(f"  Binding energies: {p1}")

    p2 = plot_admet_radar(mock_admet, "Exemestane")
    print(f"  ADMET radar: {p2}")

    p3 = plot_energy_distribution(mock_results)
    print(f"  Energy distribution: {p3}")

    p4 = draw_molecule_2d("CC(=O)Oc1ccccc1C(=O)O", "aspirin")
    print(f"  2D structure: {p4}")

    print("\nAll sample figures generated!")
