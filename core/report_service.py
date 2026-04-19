import json
from typing import Literal, Optional

from api import db_reports
from api.config import settings
from api.db import (
    get_chat_messages,
    get_docking_run,
    get_job,
    verify_job_owner,
    verify_session_owner,
)
from core.llm import complete
from core.prompts.run_report import SECTION_PROMPTS

RunType = Literal["dock", "optimize", "chat_session", "project"]
SectionKey = Literal["methods", "purpose", "clinical_significance", "what_it_did", "notes"]

ALL_SECTIONS: list[SectionKey] = [
    "methods",
    "purpose",
    "clinical_significance",
    "what_it_did",
    "notes",
]

# Sections whose prompt templates include {research_question}. Methods,
# what_it_did, and notes are data-derived — their templates must not reference
# the research question so edits to it don't drift those sections.
RQ_DEPENDENT_SECTIONS: set[SectionKey] = {"purpose", "clinical_significance"}


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------

def _verify_ownership(
    run_id: Optional[str],
    run_type: RunType,
    user_id: str,
    source_run_ids: Optional[list[str]] = None,
) -> None:
    """Normalize ValueError from db helpers to PermissionError for the route layer."""
    try:
        if run_type == "dock":
            row = get_docking_run(run_id, user_id=user_id) if run_id else None
            if not row:
                raise PermissionError("Not authorized")
        elif run_type == "optimize":
            if not run_id:
                raise PermissionError("Not authorized")
            verify_job_owner(run_id, user_id)
        elif run_type == "chat_session":
            if not run_id:
                raise PermissionError("Not authorized")
            verify_session_owner(run_id, user_id)
        elif run_type == "project":
            for rid in source_run_ids or []:
                row = get_docking_run(rid, user_id=user_id)
                if not row:
                    raise PermissionError(f"Not authorized for run {rid}")
    except ValueError as e:
        raise PermissionError(str(e)) from e


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def _find_dock_job(run_id: str) -> Optional[dict]:
    """Find the job whose result.run_id == given docking_runs.id.

    `jobs.result.run_id` is written by `run_dock_job` in api/jobs.py:161.
    """
    from api.db import _supabase

    result = (
        _supabase.table("jobs")
        .select("*")
        .eq("job_type", "dock")
        .filter("result->>run_id", "eq", run_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _bounded_chat_context(
    session_id: str,
    max_user_chars: int = 8000,
    max_artifacts: int = 20,
) -> dict:
    """Cap chat context to ~20k tokens. Drop oldest assistant excerpts first."""
    messages = get_chat_messages(session_id)  # ordered asc
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]

    user_text = "\n\n".join(m.get("content", "") for m in user_msgs)
    if len(user_text) > max_user_chars:
        user_text = user_text[:max_user_chars] + "\n\n[...truncated...]"

    assistant_excerpts: list[str] = []
    budget = 6000
    for m in reversed(assistant_msgs):
        chunk = (m.get("content") or "")[:300]
        if budget - len(chunk) < 0:
            break
        assistant_excerpts.append(chunk)
        budget -= len(chunk)
    assistant_excerpts.reverse()

    artifacts = [m.get("artifacts") for m in messages if m.get("artifacts")]
    artifacts = artifacts[-max_artifacts:]

    return {
        "user_messages_concatenated": user_text,
        "assistant_excerpts": assistant_excerpts,
        "artifacts": artifacts,
        "first_user_message": user_msgs[0].get("content") if user_msgs else None,
    }


def _prune_dock_context(dock_run: dict, job: Optional[dict]) -> dict:
    """Drop noisy fields that bloat tokens without helping the LLM."""
    pruned: dict = {
        "run_id": dock_run.get("id"),
        "best_energy": dock_run.get("best_energy"),
        "exhaustiveness": dock_run.get("exhaustiveness"),
        "center": [dock_run.get(f"center_{a}") for a in "xyz"],
        "size": [dock_run.get(f"size_{a}") for a in "xyz"],
        "proteins": dock_run.get("proteins"),
        "compounds": dock_run.get("compounds"),
    }
    if job and job.get("result"):
        r = job["result"]
        pruned["top_poses"] = (r.get("all_poses") or [])[:5]
        pruned["protein_info"] = {
            k: v
            for k, v in (r.get("protein_info") or {}).items()
            if k in {
                "title",
                "organism",
                "resolution",
                "method",
                "r_free",
                "clashscore",
                "gene_name",
                "ec_number",
                "ligands",
                "citation",
            }
        }
        pruned["uniprot"] = r.get("uniprot")
        pruned["target_summary"] = r.get("target_summary")
        pruned["admetlab"] = r.get("admetlab")
        pruned["admet"] = r.get("admet")
    return pruned


def build_context(
    run_id: Optional[str],
    run_type: RunType,
    user_id: str,
    source_run_ids: Optional[list[str]] = None,
) -> dict:
    _verify_ownership(run_id, run_type, user_id, source_run_ids)

    if run_type == "dock":
        run = get_docking_run(run_id, user_id=user_id)
        job = _find_dock_job(run_id)
        ctx = _prune_dock_context(run, job)
        proteins = run.get("proteins") or {}
        compounds = run.get("compounds") or {}
        ctx["display_title"] = (
            (compounds.get("name") or "compound")
            + " vs "
            + (proteins.get("pdb_id") or "target")
        )
        return ctx

    if run_type == "optimize":
        job = get_job(run_id)
        job_input = (job or {}).get("input") or {}
        return {
            "display_title": f"Optimization of {job_input.get('smiles', '?')}",
            "input": job_input,
            "result": (job or {}).get("result"),
        }

    if run_type == "chat_session":
        from api.db import _supabase

        resp = (
            _supabase.table("chat_sessions")
            .select("*")
            .eq("id", run_id)
            .maybe_single()
            .execute()
        )
        session = resp.data if resp else {}
        session = session or {}
        return {
            "display_title": session.get("title", "Chat session"),
            "chat": _bounded_chat_context(run_id),
        }

    # project rollup
    runs = [get_docking_run(rid, user_id=user_id) for rid in (source_run_ids or [])]
    return {
        "display_title": f"Project rollup - {len(runs)} runs",
        "runs": [
            _prune_dock_context(r, _find_dock_job(r["id"]))
            for r in runs
            if r
        ],
    }


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def synthesize_sections(
    context: dict,
    research_question: Optional[str],
    sections: list[SectionKey],
) -> dict:
    out: dict = {}
    context_json = json.dumps(context, default=str, indent=2)
    rq = research_question or "(not provided — infer from context)"
    for s in sections:
        template = SECTION_PROMPTS[s]
        if s in RQ_DEPENDENT_SECTIONS:
            prompt = template.format(
                context_json=context_json,
                research_question=rq,
            )
        else:
            prompt = template.format(context_json=context_json)
        text = complete(prompt, model=settings.openrouter_default_model)
        out[s] = text.strip()
    return out


def render_markdown(sections: dict, meta: dict) -> str:
    return (
        f"# Run Report - {meta['title']}\n\n"
        f"_{meta.get('subtitle', '')}_\n\n"
        f"## Purpose\n{sections.get('purpose', '')}\n\n"
        f"## Methods\n{sections.get('methods', '')}\n\n"
        f"## What It Did\n{sections.get('what_it_did', '')}\n\n"
        f"## Clinical Significance\n{sections.get('clinical_significance', '')}\n\n"
        f"## Additional Notes\n{sections.get('notes', '')}\n"
    )


# ---------------------------------------------------------------------------
# Service entry points
# ---------------------------------------------------------------------------

def generate_report(
    run_id: Optional[str],
    run_type: RunType,
    research_question: Optional[str],
    user_id: str,
    source_run_ids: Optional[list[str]] = None,
) -> dict:
    """First-time generation. Idempotent for non-project types."""
    if run_type != "project" and run_id:
        existing = db_reports.get_report_by_run(run_id, run_type)
        if existing:
            if existing.get("user_id") != user_id:
                raise PermissionError("Not authorized")
            return existing

    context = build_context(run_id, run_type, user_id, source_run_ids)
    sections = synthesize_sections(context, research_question, ALL_SECTIONS)

    return db_reports.insert_report(
        user_id=user_id,
        run_id=run_id,
        run_type=run_type,
        research_question=research_question,
        sections=sections,
        model=settings.openrouter_default_model,
        display_title=context.get("display_title"),
        source_run_ids=source_run_ids,
    )


def regenerate_sections(
    report_id: str,
    sections: list[SectionKey],
    research_question: Optional[str],
    user_id: str,
) -> dict:
    """Partial regen addressed by report_id."""
    existing = db_reports.get_report_by_id(report_id)
    if not existing or existing.get("user_id") != user_id:
        raise PermissionError("Not authorized")

    context = build_context(
        existing.get("run_id"),
        existing["run_type"],
        user_id,
        existing.get("source_run_ids"),
    )
    results = synthesize_sections(context, research_question, sections)

    merged_sections = dict(existing.get("sections") or {})
    merged_sections.update(results)

    return db_reports.update_report(
        report_id=report_id,
        research_question=research_question,
        sections=merged_sections,
    )


# fpdf2's default Helvetica font is Latin-1 only. LLM outputs routinely contain
# em-dashes, curly quotes, and ellipses that crash PDF rendering. Map these to
# ASCII equivalents before export. DOCX handles Unicode fine but gets sanitized
# text too — harmless and keeps both exports consistent.
_EXPORT_CHAR_MAP = {
    "\u2014": "-",   # em dash
    "\u2013": "-",   # en dash
    "\u2011": "-",   # non-breaking hyphen
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote / apostrophe
    "\u201C": '"',   # left double quote
    "\u201D": '"',   # right double quote
    "\u2026": "...", # ellipsis
    "\u00A0": " ",   # non-breaking space
}

def _sanitize_for_export(text: str) -> str:
    """Strip non-Latin-1 characters so fpdf2's core Helvetica font can render.
    Common chars get friendly ASCII fallbacks; everything else decomposes via
    NFKD and drops combining marks. Replaces what survives with '?'."""
    import unicodedata
    for k, v in _EXPORT_CHAR_MAP.items():
        text = text.replace(k, v)
    # NFKD splits Å -> A + combining ring, µ -> u, etc.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # Anything still non-latin1 gets replaced.
    return text.encode("latin-1", errors="replace").decode("latin-1")


def render_for_export(report_id: str, user_id: str) -> tuple[str, str]:
    """Return (markdown, display_title). Renders on every call — no file cache."""
    existing = db_reports.get_report_by_id(report_id)
    if not existing or existing.get("user_id") != user_id:
        raise PermissionError("Not authorized")
    title = _sanitize_for_export(existing.get("display_title") or "Run Report")
    sections = {k: _sanitize_for_export(v) for k, v in (existing.get("sections") or {}).items()}
    md = render_markdown(sections, {"title": title, "subtitle": existing.get("run_type", "")})
    return md, title
