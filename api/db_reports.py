from datetime import datetime, timezone
from typing import Any, Optional

from api.db import _supabase


# ---------------------------------------------------------------------------
# Run Reports
# ---------------------------------------------------------------------------

def insert_report(
    user_id: str,
    run_id: Optional[str],
    run_type: str,
    research_question: Optional[str],
    sections: dict,
    model: str,
    display_title: Optional[str],
    source_run_ids: Optional[list[str]] = None,
) -> dict:
    row: dict[str, Any] = {
        "user_id": user_id,
        "run_id": run_id,
        "run_type": run_type,
        "research_question": research_question,
        "sections": sections,
        "model": model,
        "display_title": display_title,
        "source_run_ids": source_run_ids,
    }
    result = _supabase.table("run_reports").insert(row).execute()
    return result.data[0]


def get_report_by_id(report_id: str) -> Optional[dict]:
    result = (
        _supabase.table("run_reports")
        .select("*")
        .eq("id", report_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def get_report_by_run(run_id: str, run_type: str) -> Optional[dict]:
    result = (
        _supabase.table("run_reports")
        .select("*")
        .eq("run_id", run_id)
        .eq("run_type", run_type)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def update_report(
    report_id: str,
    research_question: Optional[str] = None,
    sections: Optional[dict] = None,
) -> dict:
    row: dict[str, Any] = {
        "regenerated_at": datetime.now(timezone.utc).isoformat(),
    }
    if research_question is not None:
        row["research_question"] = research_question
    if sections is not None:
        row["sections"] = sections

    result = (
        _supabase.table("run_reports")
        .update(row)
        .eq("id", report_id)
        .execute()
    )
    return result.data[0]
