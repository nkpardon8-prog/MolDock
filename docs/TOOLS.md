# MoleCopilot — Tool & Software Registry

> **This is the single source of truth for all scientific tools, APIs, databases, and visualization libraries used in MoleCopilot.**
>
> **When to update this file:**
> - Adding a new tool, library, or external API
> - Replacing one tool with another
> - Removing a tool that is no longer used
> - Changing how/why a tool is used
>
> **How to add a new entry:**
> 1. Add it to the appropriate category table below
> 2. Fill in ALL columns — especially "Why This Tool" and "Alternatives Considered"
> 3. Add the date and a one-line changelog entry at the bottom
> 4. Update `requirements.txt` or `requirements-conda.txt` if it's a new dependency

---

## Molecular Docking & Structure Preparation

### AutoDock Vina
- **What it does:** Physics-based molecular docking — predicts binding poses and binding energies (kcal/mol) for small molecules against protein targets
- **Used in:** `core/dock_vina.py`
- **Why this tool:** Gold standard for academic molecular docking. Produces quantitative binding energies required for SAR studies and publication. Exhaustiveness parameter allows quality/speed tradeoff (8=fast, 32=standard, 64=publication).
- **Alternatives considered:** Glide (Schrödinger, commercial ~$15K/yr), GOLD (CCDC, commercial), DiffDock (NVIDIA, AI-based but no binding energies, worse on novel scaffolds — see `tmp/research/2026-04-05-nvidia-bionemo-vs-molecopilot.md`). Vina is the only free tool that produces reliable kcal/mol scores accepted by reviewers.
- **License:** Apache 2.0
- **Citation:** Eberhardt et al., J. Chem. Inf. Model. 2021, 61(8), 3891-3898

### RDKit
- **What it does:** Core cheminformatics toolkit — SMILES parsing/validation, 2D→3D coordinate generation (ETKDGv3), molecular descriptors (MW, LogP, TPSA, HBD, HBA, rotatable bonds), force field optimization (MMFF/UFF), 2D structure depiction, substructure search, canonical SMILES
- **Used in:** `core/admet_check.py`, `core/fetch_compounds.py`, `core/bionemo.py`, `core/generate_figures.py`, `pages/chat.py`
- **Why this tool:** The only comprehensive open-source cheminformatics toolkit. No real alternative exists — CDK (Java) is the closest but lacks Python integration. RDKit is the de facto standard used by >90% of computational chemistry Python projects.
- **Alternatives considered:** CDK (Java, no Python bindings), OpenEye (commercial), Schrödinger Canvas (commercial). Nothing comes close in the open-source Python space.
- **License:** BSD
- **Citation:** RDKit: Open-source cheminformatics, https://www.rdkit.org

### RDKit SA Score (Ertl-Schuffenhauer)
- **What it does:** Synthetic Accessibility scoring — rates molecules 1 (trivially easy to synthesize) to 10 (practically impossible). Based on fragment contributions and molecular complexity.
- **Used in:** `core/admet_check.py` (integrated into `full_admet()` and standalone `calculate_sa_score()`)
- **Why this tool:** Fast, local, no API needed. Runs on every ADMET check automatically. The standard SA scoring method used in drug discovery publications.
- **Alternatives considered:** NVIDIA ReaSyn v2 (not available yet as of April 2026), SCScore (Coley et al., requires trained model), SYBA (Vorsilak et al., Bayesian). SA Score is the most widely cited and simplest to integrate — already ships with RDKit Contrib.
- **License:** BSD (part of RDKit)
- **Citation:** Ertl & Schuffenhauer, J. Cheminformatics 2009, 1:8

### Meeko
- **What it does:** Converts molecular structures (SDF, MOL2) to PDBQT format required by AutoDock Vina. Handles torsion tree generation, atom typing, and partial charge assignment.
- **Used in:** `core/prep_ligand.py` (primary ligand preparation method)
- **Why this tool:** Purpose-built for AutoDock Vina by the Forli Lab at Scripps. More accurate torsion handling than Open Babel's PDBQT output. Recommended by Vina developers.
- **Alternatives considered:** Open Babel (used as fallback when Meeko fails on unusual chemistry), MGLTools/AutoDockTools (legacy, Python 2 only). Meeko is the modern replacement for MGLTools.
- **License:** Apache 2.0
- **Citation:** Forli Lab, Scripps Research Institute

### Open Babel
- **What it does:** Molecular format conversion — handles SDF↔MOL2↔PDB↔PDBQT and 100+ other formats. Used as fallback when Meeko cannot handle a molecule.
- **Used in:** `core/prep_ligand.py` (fallback), `core/prep_protein.py` (PDB→PDBQT conversion)
- **Why this tool:** Most comprehensive molecular format converter available. Handles edge cases (unusual atom types, non-standard residues) that Meeko cannot.
- **Alternatives considered:** No real alternative for breadth of format support. Meeko is preferred for ligands (better Vina compatibility), but Open Babel is indispensable as a fallback and for protein PDBQT conversion.
- **License:** GPL-2.0
- **Citation:** O'Boyle et al., J. Cheminformatics 2011, 3:33

### PDBFixer
- **What it does:** Protein structure repair — removes crystallographic water, adds missing hydrogens, fixes missing atoms and residues, handles non-standard residues. Part of the OpenMM ecosystem.
- **Used in:** `core/prep_protein.py`
- **Why this tool:** Purpose-built for preparing PDB structures for simulation/docking. Handles the messy reality of crystal structures (missing loops, alternate conformations, non-standard residues) better than manual cleaning.
- **Alternatives considered:** MODELLER (academic license required, complex setup), CHARMM-GUI (web-only), manual editing in PyMOL. PDBFixer is the only scriptable, open-source, Python-native solution.
- **License:** MIT
- **Citation:** Eastman et al. (OpenMM project)

### PLIP (Protein-Ligand Interaction Profiler)
- **What it does:** Identifies and categorizes non-covalent interactions between protein and ligand — hydrogen bonds, hydrophobic contacts, pi-stacking, salt bridges, water bridges, halogen bonds. Reports residue names, distances, and angles.
- **Used in:** `core/analyze_results.py` (primary interaction analysis)
- **Why this tool:** The most comprehensive open-source interaction profiler. Detects 7 interaction types vs simpler distance-based methods that only find contacts. Output is directly usable for publication figures and tables.
- **Alternatives considered:** ProLIF (also integrated as secondary method), LigPlot+ (commercial), MOE (commercial). PLIP provides the richest interaction detail in the open-source space.
- **License:** Apache 2.0
- **Citation:** Adasme et al., Nucleic Acids Res. 2021, 49(W1), W530-W534

### ProLIF
- **What it does:** Protein-ligand interaction fingerprints — binary fingerprint encoding of interactions for comparison across multiple docking poses or compounds. Secondary to PLIP.
- **Used in:** `core/analyze_results.py` (interaction fingerprinting, secondary method)
- **Why this tool:** Complements PLIP with fingerprint-based comparison. Useful for batch analysis when comparing many compounds against the same target.
- **Alternatives considered:** PLIP handles most needs. ProLIF adds the fingerprint comparison capability that PLIP lacks.
- **License:** MIT
- **Citation:** Bouysset & Fiorucci, J. Cheminformatics 2021, 13:72

---

## AI-Powered Molecular Generation

### NVIDIA MolMIM (via BioNeMo NIM)
- **What it does:** Generative molecular design — takes a seed molecule (SMILES) and generates structurally similar analogs optimized for drug-like properties (QED, pLogP) using CMA-ES evolutionary strategy in a learned latent space.
- **Used in:** `core/bionemo.py` (API wrapper), `mcp_server.py` (generate_analogs, optimize_compound tools), `pages/optimize.py` (dashboard UI)
- **Why this tool:** The collaborator specifically requested MolMIM. It provides property-directed generation (optimize for QED or LogP) which simple enumeration cannot do. The CMA-ES approach explores chemical space efficiently.
- **Alternatives considered:** REINVENT (AstraZeneca, open source but complex setup), SAFE-GPT (open source), GenMol (newer NVIDIA model, more powerful but MolMIM was specifically requested). See `tmp/research/2026-04-05-nvidia-bionemo-vs-molecopilot.md` for full comparison.
- **API endpoint:** `https://health.api.nvidia.com/v1/biology/nvidia/molmim/generate`
- **Auth:** Bearer token (NVIDIA_API_KEY in .env, free at build.nvidia.com)
- **Rate limits:** 1,000 free credits on signup
- **License:** NVIDIA API Terms of Service (proprietary model weights)
- **Citation:** NVIDIA BioNeMo, https://build.nvidia.com/nvidia/molmim-generate

---

## Biomedical Databases & APIs

### RCSB Protein Data Bank
- **What it does:** Downloads protein crystal structures (.pdb files), provides metadata (organism, resolution, method, ligands, citations), full-text search across 200K+ structures. Polymer entity endpoint provides UniProt accession, EC number, GO terms, and gene names for biological context enrichment.
- **Used in:** `core/fetch_pdb.py` (fetch_protein, search_pdb, get_protein_info)
- **Why this tool:** THE canonical source for experimentally determined protein structures. There is no alternative — all protein crystal structures are deposited here.
- **API endpoints:** `https://files.rcsb.org/download/`, `https://search.rcsb.org/`, `https://data.rcsb.org/` (including `/rest/v1/core/polymer_entity/`)
- **Auth:** None (free, public)
- **Citation:** Berman et al., Nucleic Acids Res. 2000, 28(1), 235-242

### PubChem (PUG-REST)
- **What it does:** Compound search by name, retrieves SMILES, molecular formula, MW, 3D SDF structures. 110M+ compounds.
- **Used in:** `core/fetch_compounds.py` (search_pubchem, fetch_compound_sdf)
- **Why this tool:** Largest free public chemical database. No alternative matches its coverage. The PUG-REST API is simple and well-documented.
- **API endpoint:** `https://pubchem.ncbi.nlm.nih.gov/rest/pug/`
- **Auth:** None (free, public)
- **Citation:** Kim et al., Nucleic Acids Res. 2023, 51(D1), D1373-D1380

### PubMed / NCBI Entrez
- **What it does:** Biomedical literature search — article titles, abstracts, authors, DOIs, journal info. 35M+ citations.
- **Used in:** `core/literature.py` (search_pubmed via BioPython Entrez)
- **Why this tool:** THE canonical biomedical literature database. No alternative exists for this scope.
- **API endpoint:** NCBI E-utilities via BioPython `Bio.Entrez`
- **Auth:** Optional API key (3 req/sec without, 10 req/sec with)
- **Citation:** NCBI, National Library of Medicine

### ChEMBL
- **What it does:** Retrieves known bioactive compounds and their activity data (IC50, Ki, EC50) against specific protein targets. 2.4M+ compounds, 20M+ activity records. Mechanism endpoint provides drug mechanism-of-action data. Target summary statistics (total compounds tested, best IC50, approved drugs) via `get_target_summary()`.
- **Used in:** `core/literature.py` (get_known_actives, get_target_summary via chembl_webresource_client)
- **Why this tool:** Largest open-access bioactivity database. Critical for validating docking results against experimental data and finding reference compounds.
- **Alternatives considered:** BindingDB (smaller, less API support), PubChem BioAssay (less curated). ChEMBL is the gold standard for curated activity data.
- **Auth:** None (free, public)
- **Citation:** Zdrazil et al., Nucleic Acids Res. 2024, 52(D1), D1180-D1192

### UniProt
- **What it does:** Protein function annotations, domain architecture, disease associations, subcellular location, PDB cross-references. 250M+ protein sequences. Expanded feature parsing includes active sites, binding sites, known mutations, and catalytic activity annotations.
- **Used in:** `core/literature.py` (get_uniprot_info)
- **Why this tool:** THE canonical protein knowledge base. Provides biological context that PDB structures alone cannot — function, disease relevance, known mutations.
- **API endpoint:** `https://rest.uniprot.org/uniprotkb/`
- **Auth:** None (free, public)
- **Citation:** UniProt Consortium, Nucleic Acids Res. 2023, 51(D1), D523-D531

### ADMETlab 3.0
- **What it does:** ML-predicted ADMET profiling with 119 endpoints — CYP inhibition, hERG cardiotoxicity, organ toxicity, absorption, BBB permeability, and more. Accepts SMILES input, returns comprehensive pharmacokinetic and toxicity predictions.
- **Used in:** `core/admet_check.py`
- **Why this tool:** Most comprehensive free ADMET prediction service available. 119 endpoints cover far more than RDKit descriptors alone. Useful for early-stage lead triage before expensive experimental ADMET assays.
- **Alternatives considered:** pkCSM (fewer endpoints, less accurate), SwissADME (web-only, no batch API), admetSAR (smaller model). ADMETlab 3.0 is the current state-of-the-art for ML-predicted ADMET.
- **API endpoint:** POST `https://admetlab3.scbdd.com/api/admet`
- **Auth:** None (free, public)
- **Rate limits:** 5 req/sec, ~87s per 1000 molecules
- **Note:** Server is known to be unstable; RDKit-based ADMET is used as automatic fallback when the API is unreachable.
- **License:** Free for academic use
- **Citation:** ADMETlab 3.0, Nucleic Acids Research 2024

### Natural Products Atlas
- **What it does:** Curated database of 36,500+ microbially-derived natural products with taxonomy, bioactivity data, and structure similarity search (Tanimoto). Supports text search by compound name and SMILES-based similarity search.
- **Used in:** `core/fetch_compounds.py` (search_npatlas, search_npatlas_similar), `mcp_server.py` (search_natural_products tool)
- **Why this tool:** The most comprehensive curated database of microbial natural products. Essential for Kaleem's marine natural products research — enables discovery of structurally related NPs and their known bioactivities.
- **Alternatives considered:** COCONUT (larger but less curated), DNP (commercial, Chapman & Hall), MarinLit (marine-specific but commercial). NP Atlas is the best free, curated, API-accessible option for microbial NPs.
- **API endpoint:** `https://www.npatlas.org/api/v1`
- **Auth:** None (20 req/min free tier; higher limits available with API key from support@npatlas.org)
- **License:** CC BY 4.0
- **Citation:** NP Atlas 3.0, Nucleic Acids Research 2025

---

## Bioinformatics Libraries

### BioPython
- **What it does:** PDB file parsing, PubMed/Entrez API integration (search, fetch abstracts), sequence handling.
- **Used in:** `core/literature.py` (Bio.Entrez for PubMed queries)
- **Why this tool:** Standard Python bioinformatics library. Provides the official NCBI Entrez API client that handles rate limiting, retries, and result parsing.
- **Alternatives considered:** Direct HTTP requests to NCBI (more error-prone, no built-in rate limiting). BioPython's Entrez module is the recommended access method per NCBI documentation.
- **License:** BSD-like (Biopython License)
- **Citation:** Cock et al., Bioinformatics 2009, 25(11), 1422-1423

---

## Visualization

### py3Dmol
- **What it does:** Interactive 3D molecular visualization in the browser — renders protein structures (cartoon, stick, sphere), ligand poses, surfaces, hydrogen bond networks. Based on 3Dmol.js.
- **Used in:** `components/mol3d.py` (render_complex, render_protein)
- **Why this tool:** Only open-source 3D molecular viewer that integrates with Streamlit (via stmol). Allows interactive rotation, zoom, style changes directly in the dashboard.
- **Alternatives considered:** NGLView (Jupyter-only, no Streamlit support), PyMOL (desktop app, not embeddable in web), Mol* (complex setup). py3Dmol + stmol is the only viable option for Streamlit-embedded 3D visualization.
- **License:** BSD
- **Citation:** Rego & Koes, Bioinformatics 2015, 31(8), 1322-1324

### Plotly
- **What it does:** Interactive charts — binding energy bar charts (color-coded by threshold), ADMET radar diagrams, energy distribution histograms, SA score comparisons.
- **Used in:** `components/charts.py`, `pages/optimize.py`, `pages/admet.py`
- **Why this tool:** Native Streamlit integration (`st.plotly_chart`), interactive hover/zoom, publication-quality output. Dark theme support matches the dashboard design.
- **Alternatives considered:** Matplotlib (static only, no interactivity in Streamlit), Bokeh (less Streamlit support), Altair (limited chart types). Plotly is the best match for interactive scientific dashboards.
- **License:** MIT
- **Citation:** Plotly Technologies Inc., https://plotly.com

### Matplotlib
- **What it does:** Static publication-quality figures — energy distribution plots, 2D molecular structure grids, docking result summaries for export to reports.
- **Used in:** `core/generate_figures.py`
- **Why this tool:** Standard for publication figures in scientific Python. Used specifically for static images saved to reports (DOCX/PDF export), where Plotly's interactivity isn't needed.
- **Alternatives considered:** Plotly (used for dashboard, but static export is harder). Matplotlib is the standard for print-ready scientific figures.
- **License:** PSF
- **Citation:** Hunter, Computing in Science & Engineering 2007, 9(3), 90-95

---

## AI-Powered Research

### Perplexity Sonar Pro
- **What it does:** AI-powered literature search with citations — summarizes research topics, returns source URLs, filters by timeframe. Used in the Literature page's "AI Research" tab.
- **Used in:** `core/literature.py` (search_perplexity)
- **Why this tool:** Provides AI-synthesized research summaries with source citations, which PubMed keyword search cannot do. Useful for rapid literature review and identifying trends.
- **Alternatives considered:** OpenAI + Bing search (more complex setup), Google Scholar API (no official API), Semantic Scholar (no summarization). Perplexity is the simplest API for cited AI research summaries.
- **API endpoint:** `https://api.perplexity.ai/chat/completions` (model: `sonar-pro`)
- **Auth:** API key (PERPLEXITY_API_KEY in .env)
- **License:** Commercial API
- **Citation:** Perplexity AI, https://www.perplexity.ai

---

## Changelog

| Date | Change | Tool | Author |
|---|---|---|---|
| 2026-03-30 | Initial pipeline — Vina, RDKit, Meeko, OpenBabel, PDBFixer, PLIP, BioPython | All core tools | MoleCopilot v1 |
| 2026-03-30 | Added PubChem, RCSB PDB, PubMed, ChEMBL, UniProt API integrations | Database APIs | MoleCopilot v1 |
| 2026-03-30 | Added py3Dmol, Plotly, Matplotlib for visualization | Visualization | MoleCopilot v1 |
| 2026-04-01 | Added Perplexity Sonar Pro for AI-powered literature search | Perplexity | Literature update |
| 2026-04-05 | Added NVIDIA MolMIM for generative molecular design | MolMIM | BioNeMo integration |
| 2026-04-05 | Added RDKit SA Score for synthetic accessibility assessment | SA Score | BioNeMo integration |
| 2026-04-05 | Added ProLIF for interaction fingerprinting | ProLIF | Analysis update |
| 2026-04-13 | Added ADMETlab 3.0 for ML-predicted ADMET profiling (119 endpoints) | ADMETlab 3.0 | ADMET integration |
| 2026-04-13 | Added Natural Products Atlas for microbial NP search and similarity | NP Atlas | NP Atlas integration |
| 2026-04-13 | Updated RCSB PDB entry: documented polymer_entity endpoint for UniProt/EC/GO enrichment | RCSB PDB | Protein enrichment |
| 2026-04-13 | Updated UniProt entry: documented expanded feature parsing (active sites, binding sites, mutations) | UniProt | Protein enrichment |
| 2026-04-13 | Updated ChEMBL entry: documented mechanism endpoint and target summary statistics | ChEMBL | Protein enrichment |
| 2026-04-13 | Added search_natural_products MCP tool and enriched protein_info with ChEMBL target summary | MCP Server | Tool registration |

---

> **Maintenance note:** This file is referenced by `CLAUDE.md` and should be updated whenever tools are added, removed, or replaced. When writing a Methods section for publication, use this file as the authoritative list. Every tool here has been verified as actively used in the codebase — no installed-but-unused dependencies are listed.
