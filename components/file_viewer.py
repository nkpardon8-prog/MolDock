"""Reusable file output panel for docking results."""
import streamlit as st
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class OutputFile:
    path: str
    role: str  # "receptor", "ligand", "docked"
    label: Optional[str] = None


ROLE_CONFIG = {
    "receptor": {"icon": "🧬", "badge": "Receptor"},
    "ligand":   {"icon": "💊", "badge": "Ligand"},
    "docked":   {"icon": "🎯", "badge": "Docked"},
}


@st.cache_data
def _parse_pdbqt_remarks(filepath: str) -> dict:
    """Extract VINA RESULT energy, pose count, SMILES from PDBQT."""
    energy, smiles, n_poses = None, None, 0
    with open(filepath) as f:
        for line in f:
            if line.startswith("REMARK VINA RESULT:"):
                if energy is None:
                    energy = float(line.split()[3])
            elif line.startswith("REMARK SMILES ") and "IDX" not in line:
                smiles = line.split(None, 2)[2].strip()
            elif line.startswith("MODEL"):
                n_poses += 1
    return {"energy": energy, "smiles": smiles, "n_poses": n_poses}


def _relative_path(filepath: str) -> str:
    """Strip project root, show relative path."""
    try:
        return str(Path(filepath).relative_to(PROJECT_ROOT))
    except ValueError:
        return filepath


def _file_size_str(filepath: str) -> str:
    """Human-readable file size."""
    size = Path(filepath).stat().st_size
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _render_3d_viewer(file: OutputFile):
    """Render inline 3D viewer for a file, handling format conversion."""
    from stmol import showmol
    import py3Dmol

    p = Path(file.path)
    ext = p.suffix.lower()

    if file.role == "receptor":
        # For receptor files, use render_protein if PDB, convert if PDBQT
        if ext == ".pdbqt":
            try:
                from core.utils import pdbqt_to_pdb
                pdb_path = pdbqt_to_pdb(file.path)
            except Exception as exc:
                st.warning(f"Could not convert PDBQT: {exc}")
                return
        elif ext == ".pdb":
            pdb_path = file.path
        else:
            st.warning(f"Unsupported format for 3D view: {ext}")
            return
        from components.mol3d import render_protein
        view = render_protein(pdb_path, style="cartoon")
        view.setBackgroundColor("#1a1a2e")
        showmol(view, height=400, width=700)

    else:
        # For ligand/docked files — render as sticks
        if ext == ".pdbqt":
            try:
                from core.utils import pdbqt_to_pdb
                pdb_path = pdbqt_to_pdb(file.path)
            except Exception as exc:
                st.warning(f"Could not convert PDBQT: {exc}")
                return
            fmt = "pdb"
        elif ext in (".pdb", ".sdf", ".mol2"):
            pdb_path = file.path
            fmt = ext.lstrip(".")
        else:
            st.warning(f"Unsupported format for 3D view: {ext}")
            return

        view = py3Dmol.view(width=700, height=400)
        with open(pdb_path) as f:
            view.addModel(f.read(), fmt)
        view.setStyle({"stick": {"colorscheme": "greenCarbon", "radius": 0.2}})
        view.setBackgroundColor("#1a1a2e")
        view.zoomTo()
        showmol(view, height=400, width=700)


def _render_card(file: OutputFile, key_prefix: str, idx: int):
    """Render a single file card with metadata, actions."""
    p = Path(file.path)
    if not p.is_file():
        st.warning(f"File not found: {_relative_path(file.path)}")
        return

    cfg = ROLE_CONFIG.get(file.role, {"icon": "📄", "badge": file.role})
    label = file.label or p.stem
    ext = p.suffix.upper().lstrip(".")

    # Header: icon + name + badge + size
    st.markdown(f"**{cfg['icon']} {label}** &nbsp; `{ext}` &nbsp; {_file_size_str(file.path)}")
    st.caption(_relative_path(file.path))

    # Metadata for docked files
    if file.role == "docked" and p.suffix.lower() == ".pdbqt":
        meta = _parse_pdbqt_remarks(file.path)
        cols = st.columns(3)
        if meta["energy"] is not None:
            cols[0].metric("Binding Energy", f"{meta['energy']:.1f} kcal/mol")
        if meta["n_poses"]:
            cols[1].metric("Poses", meta["n_poses"])
        if meta["smiles"]:
            cols[2].code(meta["smiles"], language=None)

    # Action buttons
    btn_cols = st.columns(3)
    k = f"{key_prefix}_{idx}"

    with btn_cols[0]:
        with open(file.path, "rb") as f:
            st.download_button(
                "Download", f.read(), file_name=p.name,
                mime="application/octet-stream", key=f"dl_{k}",
            )

    with btn_cols[1]:
        if st.button("View 3D", key=f"3d_{k}"):
            st.session_state[f"show_3d_{k}"] = not st.session_state.get(f"show_3d_{k}", False)

    with btn_cols[2]:
        if st.button("View Raw", key=f"raw_{k}"):
            st.session_state[f"show_raw_{k}"] = not st.session_state.get(f"show_raw_{k}", False)

    # Inline 3D viewer
    if st.session_state.get(f"show_3d_{k}", False):
        _render_3d_viewer(file)

    # Raw file viewer
    if st.session_state.get(f"show_raw_{k}", False):
        with open(file.path) as f:
            content = f.read()
        st.code(content[:10000], language=None)
        if len(content) > 10000:
            st.caption(f"Showing first 10,000 of {len(content):,} characters")


def render_file_panel(files: list[OutputFile], panel_id: str = ""):
    """Render file output panel for a list of files.

    Parameters
    ----------
    files : list[OutputFile]
        Files to display as cards.
    panel_id : str, optional
        Unique prefix for widget keys. Defaults to hash of first file path.
    """
    if not files:
        return
    if not panel_id:
        panel_id = str(hash(files[0].path))[:8]
    for idx, file in enumerate(files):
        _render_card(file, key_prefix=panel_id, idx=idx)
        if idx < len(files) - 1:
            st.divider()
