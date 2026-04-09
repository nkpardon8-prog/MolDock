# MoleCopilot

Molecular docking research agent + web dashboard. Full domain context is in the global CLAUDE.md.

## Quick reference
- Core scripts: core/ (each module has standalone demo via __main__)
- MCP server: mcp_server.py (22 tools via FastMCP)
- Dashboard: app.py (Streamlit, 8 pages)
- Database: molecopilot.db (SQLite, auto-created)
- Data: data/{proteins,ligands,results,libraries}/
- Reports: reports/

## Development
- Conda env: molecopilot (Python 3.12)
- Run dashboard: conda run -n molecopilot streamlit run app.py
- Run tests: conda run -n molecopilot python tests/test_pipeline.py
- Verify deps: conda run -n molecopilot python tests/verify_imports.py

## Architecture
- `app.py` — Streamlit entry point (st.navigation)
- `pages/` — 8 dashboard pages (dashboard, dock, optimize, results, admet, 3d viewer, literature, chat)
- `components/` — database.py (SQLite), charts.py (Plotly), mol3d.py (py3Dmol/stmol)
- `core/` — science scripts (fetch, prep, dock, analyze, export, bionemo)
- `mcp_server.py` — MCP server wrapping core/ functions (25 tools)

## Tool Registry
- **All scientific tools, APIs, and databases are documented in `docs/TOOLS.md`**
- When adding or replacing any tool, update `docs/TOOLS.md` first
- That file is the authoritative reference for Methods sections in publications
