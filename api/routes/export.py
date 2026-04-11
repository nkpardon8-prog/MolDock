from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from api.config import settings
from api.schemas import ExportRequest

router = APIRouter(prefix="/export", tags=["export"])


def _validate_results_dir(results_dir: str) -> Path:
    """Validate results_dir stays within data_root. Prevents path traversal."""
    root = Path(settings.data_root).resolve()
    full = (root / results_dir).resolve()
    if not str(full).startswith(str(root)):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    return full


@router.post("")
def export_report(request: Request, body: ExportRequest):
    fmt = body.output_format.lower()

    if fmt == "docx":
        from core.export_docs import export_docx

        markdown_text = _load_results_markdown(body.results_dir, body.project_name)
        try:
            output_path = export_docx(
                markdown_text=markdown_text,
                title=body.project_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return FileResponse(
            path=output_path,
            filename=Path(output_path).name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    elif fmt == "pdf":
        from core.export_docs import export_pdf

        markdown_text = _load_results_markdown(body.results_dir, body.project_name)
        try:
            output_path = export_pdf(
                markdown_text=markdown_text,
                title=body.project_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return FileResponse(
            path=output_path,
            filename=Path(output_path).name,
            media_type="application/pdf",
        )

    elif fmt == "xlsx":
        from core.export_docs import export_xlsx

        data = _load_results_data(body.results_dir, body.project_name)
        try:
            output_path = export_xlsx(
                data=data,
                title=body.project_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return FileResponse(
            path=output_path,
            filename=Path(output_path).name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {fmt}. Use 'docx', 'pdf', or 'xlsx'.",
        )


def _load_results_markdown(results_dir: str | None, project_name: str) -> str:
    if results_dir:
        validated = _validate_results_dir(results_dir)
        md_path = validated / "report.md"
        if md_path.is_file():
            return md_path.read_text(encoding="utf-8")

    return f"# {project_name}\n\nNo results data available for export.\n"


def _load_results_data(results_dir: str | None, project_name: str) -> dict:
    import json

    if results_dir:
        validated = _validate_results_dir(results_dir)
        json_path = validated / "results.json"
        if json_path.is_file():
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
            return {project_name: raw}

    return {project_name: [{"Note": "No data available"}]}
