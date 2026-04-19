"""Section prompts for run report synthesis.

Contract:
- Methods, What-It-Did, Notes take ONLY `{context_json}`.
- Purpose, Clinical Significance take `{context_json}` AND `{research_question}`.
- Every prompt ends with the same format guidance.
- Templates are consumed by `str.format()` — literal braces are doubled.
"""

PROMPT_METHODS = """You are writing the Methods section of a molecular docking run report for a pharmacology audience.

The structured context below describes a MolCopilot pipeline execution. Depending on the run_type, it may contain fields from the dock pipeline (fetch_protein, detect_binding_site, prepare_protein, AutoDock Vina docking, ADMET analysis), an optimize run, a chat session, or a project rollup of multiple runs.

Write a Methods section, 2-4 short paragraphs, walking through the pipeline in the order it executed. Reference concrete parameters actually present in the context: PDB ID, exhaustiveness, grid box center and size (in Angstroms), compound SMILES or name, ADMET tool if present (e.g. ADMETlab), any literature enrichment (UniProt, target_summary). Be precise. Use pharmacology conventions (kcal/mol for binding energy, Angstroms for distances).

Do not invent steps not present in the context. Do not list parameters you don't have values for.

Context:
{context_json}

Return plain markdown. No preamble. No disclaimers. If data is missing from the context, say so plainly rather than speculating."""


PROMPT_PURPOSE = """You are writing the Purpose section of a molecular docking run report for a pharmacology audience.

The Purpose section answers: why was this run performed? What question was the researcher trying to answer?

The user's stated research question is below. If it is "(not provided — infer from context)", infer the purpose from the context — use target_summary, uniprot.disease_associations, the compound's known class or natural product source, and the choice of protein target. Marine natural products against cancer targets, aromatase inhibitors for breast cancer, BACE1 binders for Alzheimer's — frame accordingly when the data supports it.

Write 1-2 tight paragraphs. Grounded in what the context actually shows. Avoid generic platitudes about "drug discovery".

Research question:
{research_question}

Context:
{context_json}

Return plain markdown. No preamble. No disclaimers. If data is missing from the context, say so plainly rather than speculating."""


PROMPT_CLINICAL = """You are writing the Clinical Significance section of a molecular docking run report for a pharmacology audience.

Frame the implications of this run for drug discovery. Use disease associations from uniprot.disease_associations, therapeutic context from target_summary, and the compound's drug-likeness profile (Lipinski, Veber, ADMET scores) if present. Name the disease or therapeutic area explicitly. If binding energy is strong (more negative than -7 kcal/mol), say the compound is worth follow-up; if weaker, say so plainly.

The research question below may narrow the framing. If it is "(not provided — infer from context)", infer clinical relevance from the target's disease links.

Write 1-3 paragraphs. Be specific about which disease, which pathway, which patient population — never just "various diseases".

Research question:
{research_question}

Context:
{context_json}

Return plain markdown. No preamble. No disclaimers. If data is missing from the context, say so plainly rather than speculating."""


PROMPT_WHAT_IT_DID = """You are writing the What It Did section of a molecular docking run report for a pharmacology audience.

This section reports results as they came out — the numbers, not the interpretation. Extract from the context: best binding energy (kcal/mol), number of poses, energy distribution if multiple poses, any ADMET scores (drug_likeness_score, sa_score, Lipinski pass/fail), interaction summary if present. For optimize runs, report generated molecule count, similarity range, and any standout hits. For chat sessions, summarize what docking runs or analyses were actually executed during the session. For project rollups, give a ranked list of the top runs by binding energy.

Write 2-3 paragraphs plus a short bullet list of key numbers if it helps. Report what happened — do not editorialize.

Context:
{context_json}

Return plain markdown. No preamble. No disclaimers. If data is missing from the context, say so plainly rather than speculating."""


PROMPT_NOTES = """You are writing the Additional Notes section of a molecular docking run report for a pharmacology audience.

Use this section for caveats, limitations, and follow-up suggestions grounded in the context. Examples worth flagging when supported: low crystal structure resolution (>3.0 Å), high clashscore, missing residues, a co-crystallized ligand that was present in the original PDB, a compound that fails Lipinski, a low SA score, a borderline binding energy that warrants a rerun at higher exhaustiveness, or an ADMET liability (CYP inhibition, hERG risk, high logP).

If nothing notable is flagged by the data, say so in one sentence. Do not invent concerns.

Context:
{context_json}

Return plain markdown. No preamble. No disclaimers. If data is missing from the context, say so plainly rather than speculating."""


SECTION_PROMPTS = {
    "methods": PROMPT_METHODS,
    "purpose": PROMPT_PURPOSE,
    "clinical_significance": PROMPT_CLINICAL,
    "what_it_did": PROMPT_WHAT_IT_DID,
    "notes": PROMPT_NOTES,
}
