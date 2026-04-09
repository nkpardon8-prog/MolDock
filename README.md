# MoleCopilot — Molecular Docking & More

A computational drug discovery platform with an interactive web dashboard. Built for Professor Kaleem Mohammed (University of Utah, Pharmacology & Biochemistry) to streamline marine natural product research against cancer and neurodegenerative disease targets.

## Quick Start

**Via Claude Code (natural language):**
```
/dock thymoquinone against DNMT1 (PDB: 3PTA)
/screen "aromatase inhibitors" against 3S7S top 20
/admet CC(=O)Oc1ccccc1C(=O)O
/dashboard
```

**Via Web Dashboard:**
```bash
conda run -n molecopilot streamlit run app.py
# Opens at http://localhost:8501
```

## Web Dashboard

7-page Streamlit application:

| Page | What It Does |
|------|-------------|
| **Dashboard** | Stats, recent runs, top hits chart, quick actions |
| **Dock** | Submit docking jobs with forms, see results inline |
| **Results** | Browse, filter, compare all past docking runs |
| **ADMET** | Drug-likeness analysis with radar plots |
| **3D Viewer** | Interactive protein-ligand visualization (py3Dmol) |
| **Literature** | PubMed, ChEMBL, UniProt search |
| **Chat** | Claude Code AI chatbot with full tool access |

## MCP Tools (22)

All tools are available via Claude Code and the web dashboard.

**Core Pipeline:** fetch_protein, prepare_protein, fetch_compound, prepare_ligand, dock, full_pipeline

**Batch:** batch_prepare_ligands, batch_dock, batch_admet

**Analysis:** detect_binding_site, analyze_interactions, rank_results, admet_check, compare_compounds

**Database:** search_proteins, search_compounds, search_literature, get_known_actives

**Output:** draw_molecule, protein_info, generate_report, export_report

## Project Structure

```
├── app.py                  # Streamlit dashboard entry point
├── pages/                  # 7 dashboard pages
├── components/             # Database, charts, 3D viewer
│   ├── database.py         # SQLite persistence
│   ├── charts.py           # Plotly interactive charts
│   └── mol3d.py            # py3Dmol/stmol wrapper
├── core/                   # Science scripts
│   ├── fetch_pdb.py        # RCSB PDB access
│   ├── prep_protein.py     # PDBFixer + PDBQT conversion
│   ├── dock_vina.py        # AutoDock Vina
│   ├── admet_check.py      # Lipinski/Veber scoring
│   ├── analyze_results.py  # PLIP interactions
│   ├── literature.py       # PubMed + ChEMBL + UniProt
│   └── export_docs.py      # Word/PDF/Excel export
├── mcp_server.py           # MCP server (22 tools)
├── data/                   # Proteins, ligands, results
├── reports/                # Generated reports + figures
└── molecopilot.db          # SQLite database (auto-created)
```

## Setup

```bash
git clone <repo-url>
cd MolecularDocking-More
bash setup.sh
```

Requires: conda (Miniconda or Anaconda)

## Dependencies

**Conda-forge:** vina, rdkit, pdbfixer, openmm, openbabel, prolif, numpy, pandas, matplotlib, seaborn, pillow

**pip:** meeko, plip, mcp, streamlit, stmol, plotly, py3Dmol, biopython, python-docx, fpdf2, openpyxl, chembl-webresource-client

## External APIs (all free, no keys required)

- RCSB PDB — protein structures
- PubChem — compound data
- ChEMBL — bioactivity data
- UniProt — protein annotations
- PubMed — literature search
