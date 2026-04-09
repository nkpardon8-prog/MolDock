import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "molecopilot.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict, parsing JSON fields."""
    if row is None:
        return None
    d = dict(row)
    json_fields = [
        "binding_site_json",
        "admet_json",
        "all_energies_json",
        "interactions_json",
        "results_json",
        "tags_json",
    ]
    for field in json_fields:
        if field in d and d[field] is not None:
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def _rows_to_dicts(rows):
    """Convert a list of sqlite3.Row objects to a list of plain dicts."""
    return [_row_to_dict(row) for row in rows]


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS proteins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pdb_id TEXT UNIQUE NOT NULL,
                title TEXT,
                organism TEXT,
                resolution REAL,
                method TEXT,
                pdb_path TEXT,
                pdbqt_path TEXT,
                binding_site_json TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS compounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                smiles TEXT,
                cid TEXT,
                sdf_path TEXT,
                pdbqt_path TEXT,
                admet_json TEXT,
                drug_likeness_score REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS docking_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protein_id INTEGER NOT NULL,
                compound_id INTEGER NOT NULL,
                best_energy REAL,
                all_energies_json TEXT,
                exhaustiveness INTEGER,
                center_x REAL,
                center_y REAL,
                center_z REAL,
                size_x REAL,
                size_y REAL,
                size_z REAL,
                output_path TEXT,
                interactions_json TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (protein_id) REFERENCES proteins(id),
                FOREIGN KEY (compound_id) REFERENCES compounds(id)
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS literature_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                source_type TEXT NOT NULL,
                results_json TEXT NOT NULL,
                tags_json TEXT DEFAULT '[]',
                timeframe TEXT DEFAULT NULL,
                result_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_lit_search_source_date
                ON literature_searches(source_type, created_at DESC);
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Proteins
# ---------------------------------------------------------------------------

def save_protein(pdb_id, title=None, organism=None, resolution=None,
                 method=None, pdb_path=None, pdbqt_path=None,
                 binding_site=None):
    """Insert or update a protein record (merge non-None fields). Returns the row id."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM proteins WHERE pdb_id = ?", (pdb_id,)
        ).fetchone()

        binding_site_json = json.dumps(binding_site) if binding_site else None

        if existing:
            # Merge: only update fields that are not None
            cursor = conn.execute(
                """UPDATE proteins SET
                       title = COALESCE(?, title),
                       organism = COALESCE(?, organism),
                       resolution = COALESCE(?, resolution),
                       method = COALESCE(?, method),
                       pdb_path = COALESCE(?, pdb_path),
                       pdbqt_path = COALESCE(?, pdbqt_path),
                       binding_site_json = COALESCE(?, binding_site_json)
                   WHERE pdb_id = ?""",
                (title, organism, resolution, method, pdb_path,
                 pdbqt_path, binding_site_json, pdb_id),
            )
            conn.commit()
            return existing["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO proteins
                   (pdb_id, title, organism, resolution, method, pdb_path,
                    pdbqt_path, binding_site_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pdb_id, title, organism, resolution, method, pdb_path,
                 pdbqt_path, binding_site_json, datetime.utcnow().isoformat()),
            )
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


def get_all_proteins():
    """Return all proteins as a list of dicts."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM proteins ORDER BY created_at DESC"
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_protein_by_pdb_id(pdb_id):
    """Return a single protein dict by PDB ID, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM proteins WHERE pdb_id = ?", (pdb_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Compounds
# ---------------------------------------------------------------------------

def save_compound(name=None, smiles=None, cid=None, sdf_path=None,
                  pdbqt_path=None, admet_data=None):
    """Insert or update a compound record (dedup by SMILES, then CID). Returns the row id.

    If admet_data is provided, drug_likeness_score is extracted from it.
    """
    conn = get_connection()
    try:
        admet_json = json.dumps(admet_data) if admet_data else None
        drug_likeness_score = None
        if admet_data and isinstance(admet_data, dict):
            drug_likeness_score = admet_data.get("drug_likeness_score")
            if drug_likeness_score is None:
                violations = 0
                mw = admet_data.get("molecular_weight") or admet_data.get("MW")
                logp = admet_data.get("logp") or admet_data.get("LogP")
                hbd = admet_data.get("hbd") or admet_data.get("HBD")
                hba = admet_data.get("hba") or admet_data.get("HBA")
                if mw is not None and float(mw) > 500:
                    violations += 1
                if logp is not None and float(logp) > 5:
                    violations += 1
                if hbd is not None and float(hbd) > 5:
                    violations += 1
                if hba is not None and float(hba) > 10:
                    violations += 1
                if any(v is not None for v in [mw, logp, hbd, hba]):
                    drug_likeness_score = round(1.0 - (violations / 4.0), 2)

        # Dedup: check by SMILES first, then by CID
        existing = None
        if smiles:
            existing = conn.execute(
                "SELECT * FROM compounds WHERE smiles = ?", (smiles,)
            ).fetchone()
        if not existing and cid:
            existing = conn.execute(
                "SELECT * FROM compounds WHERE cid = ?", (str(cid),)
            ).fetchone()

        if existing:
            cursor = conn.execute(
                """UPDATE compounds SET
                       name = COALESCE(?, name),
                       smiles = COALESCE(?, smiles),
                       cid = COALESCE(?, cid),
                       sdf_path = COALESCE(?, sdf_path),
                       pdbqt_path = COALESCE(?, pdbqt_path),
                       admet_json = COALESCE(?, admet_json),
                       drug_likeness_score = COALESCE(?, drug_likeness_score)
                   WHERE id = ?""",
                (name, smiles, str(cid) if cid else None, sdf_path,
                 pdbqt_path, admet_json, drug_likeness_score, existing["id"]),
            )
            conn.commit()
            return existing["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO compounds
                   (name, smiles, cid, sdf_path, pdbqt_path, admet_json,
                    drug_likeness_score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, smiles, str(cid) if cid else None, sdf_path,
                 pdbqt_path, admet_json, drug_likeness_score,
                 datetime.utcnow().isoformat()),
            )
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


def get_all_compounds():
    """Return all compounds as a list of dicts."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM compounds ORDER BY created_at DESC"
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_compound_by_smiles(smiles):
    """Return a single compound dict by SMILES, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM compounds WHERE smiles = ?", (smiles,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Docking Runs
# ---------------------------------------------------------------------------

def save_docking_run(protein_id, compound_id, best_energy, all_energies=None,
                     exhaustiveness=32, center=(0, 0, 0), size=(20, 20, 20),
                     output_path=None, interactions=None):
    """Save a docking run. Returns the row id.

    Parameters
    ----------
    all_energies : list of float — all pose energies
    center : tuple (x, y, z) — grid box center
    size : tuple (x, y, z) — grid box dimensions
    interactions : dict — PLIP interaction data
    """
    conn = get_connection()
    try:
        all_energies_json = json.dumps(all_energies) if all_energies else None
        interactions_json = json.dumps(interactions) if interactions else None
        cx, cy, cz = center
        sx, sy, sz = size
        cursor = conn.execute(
            """INSERT INTO docking_runs
               (protein_id, compound_id, best_energy, all_energies_json,
                exhaustiveness, center_x, center_y, center_z,
                size_x, size_y, size_z, output_path, interactions_json,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                protein_id,
                compound_id,
                best_energy,
                all_energies_json,
                exhaustiveness,
                cx, cy, cz,
                sx, sy, sz,
                output_path,
                interactions_json,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_recent_docking_runs(limit=10):
    """Return the most recent docking runs with protein/compound names."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT
                   dr.id,
                   dr.best_energy,
                   dr.exhaustiveness,
                   dr.output_path,
                   dr.all_energies_json,
                   dr.interactions_json,
                   dr.created_at,
                   p.pdb_id AS protein_pdb_id,
                   p.title AS protein_title,
                   c.name AS compound_name,
                   c.smiles AS compound_smiles
               FROM docking_runs dr
               JOIN proteins p ON dr.protein_id = p.id
               JOIN compounds c ON dr.compound_id = c.id
               ORDER BY dr.created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_docking_runs(protein_id=None, energy_min=None, energy_max=None,
                     limit=100):
    """Return docking runs with optional filters."""
    conn = get_connection()
    try:
        query = """
            SELECT
                dr.*,
                p.pdb_id AS protein_pdb_id,
                p.title AS protein_title,
                c.name AS compound_name,
                c.smiles AS compound_smiles
            FROM docking_runs dr
            JOIN proteins p ON dr.protein_id = p.id
            JOIN compounds c ON dr.compound_id = c.id
            WHERE 1=1
        """
        params = []

        if protein_id is not None:
            query += " AND dr.protein_id = ?"
            params.append(protein_id)
        if energy_min is not None:
            query += " AND dr.best_energy >= ?"
            params.append(energy_min)
        if energy_max is not None:
            query += " AND dr.best_energy <= ?"
            params.append(energy_max)

        query += " ORDER BY dr.best_energy ASC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_docking_run(run_id):
    """Return a single docking run with full details, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT
                   dr.*,
                   p.pdb_id AS protein_pdb_id,
                   p.title AS protein_title,
                   p.pdb_path AS protein_pdb_path,
                   p.pdbqt_path AS protein_pdbqt_path,
                   p.binding_site_json,
                   c.name AS compound_name,
                   c.smiles AS compound_smiles,
                   c.admet_json,
                   c.drug_likeness_score
               FROM docking_runs dr
               JOIN proteins p ON dr.protein_id = p.id
               JOIN compounds c ON dr.compound_id = c.id
               WHERE dr.id = ?""",
            (run_id,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Chat History
# ---------------------------------------------------------------------------

def save_chat_message(role, content):
    """Save a chat message. Returns the row id."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO chat_history (role, content, created_at)
               VALUES (?, ?, ?)""",
            (role, content, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_chat_history(limit=50):
    """Return the most recent chat messages (oldest first within the window)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM (
                   SELECT * FROM chat_history
                   ORDER BY created_at DESC
                   LIMIT ?
               ) sub
               ORDER BY created_at ASC""",
            (limit,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def get_db_snapshot():
    """Return current max IDs for proteins, compounds, docking_runs.
    Used to detect new records added between two points in time."""
    conn = get_connection()
    try:
        return {
            "max_protein_id": conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM proteins"
            ).fetchone()[0],
            "max_compound_id": conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM compounds"
            ).fetchone()[0],
            "max_run_id": conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM docking_runs"
            ).fetchone()[0],
        }
    finally:
        conn.close()


def get_new_records_since(snapshot):
    """Return records added since a snapshot from get_db_snapshot()."""
    conn = get_connection()
    try:
        new_runs = _rows_to_dicts(conn.execute(
            """SELECT dr.*, p.pdb_id AS protein_pdb_id, p.title AS protein_title,
                      c.name AS compound_name, c.smiles AS compound_smiles,
                      c.admet_json, c.drug_likeness_score
               FROM docking_runs dr
               JOIN proteins p ON dr.protein_id = p.id
               JOIN compounds c ON dr.compound_id = c.id
               WHERE dr.id > ?
               ORDER BY dr.id""",
            (snapshot["max_run_id"],)
        ).fetchall())

        new_compounds = _rows_to_dicts(conn.execute(
            """SELECT * FROM compounds WHERE id > ?
               ORDER BY id""",
            (snapshot["max_compound_id"],)
        ).fetchall())

        new_proteins = _rows_to_dicts(conn.execute(
            """SELECT * FROM proteins WHERE id > ?
               ORDER BY id""",
            (snapshot["max_protein_id"],)
        ).fetchall())

        return {
            "docking_runs": new_runs,
            "compounds": new_compounds,
            "proteins": new_proteins,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Literature Searches
# ---------------------------------------------------------------------------


def _compute_result_count(source_type, results):
    """Source-aware result count extraction."""
    if source_type == "pubmed" and isinstance(results, list):
        return len(results)
    elif source_type == "chembl" and isinstance(results, dict):
        return len(results.get("compounds", []))
    elif source_type == "perplexity" and isinstance(results, dict):
        sr = results.get("search_results", [])
        return len(sr) if sr else len(results.get("citations", []))
    elif source_type == "uniprot":
        return 1
    elif isinstance(results, list):
        return len(results)
    return 1


def save_literature_search(query, source_type, results, tags=None, timeframe=None):
    """Upsert a search — if (query, source_type) exists, update it; otherwise insert.
    Returns the row id."""
    conn = get_connection()
    try:
        results_json = json.dumps(results)
        tags_json = json.dumps(tags or [])
        result_count = _compute_result_count(source_type, results)
        now = datetime.utcnow().isoformat()

        existing = conn.execute(
            "SELECT id FROM literature_searches WHERE query = ? AND source_type = ?",
            (query, source_type),
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE literature_searches SET
                       results_json = ?, tags_json = ?, result_count = ?,
                       timeframe = COALESCE(?, timeframe), updated_at = ?
                   WHERE id = ?""",
                (results_json, tags_json, result_count, timeframe, now, existing["id"]),
            )
            conn.commit()
            return existing["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO literature_searches
                   (query, source_type, results_json, tags_json, timeframe,
                    result_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (query, source_type, results_json, tags_json, timeframe,
                 result_count, now, now),
            )
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


def get_literature_searches(source_type=None, tag=None, limit=50):
    """Return saved searches, optionally filtered by source_type or tag.
    Ordered by created_at DESC."""
    conn = get_connection()
    try:
        query = "SELECT * FROM literature_searches WHERE 1=1"
        params = []

        if source_type is not None:
            query += " AND source_type = ?"
            params.append(source_type)
        if tag is not None:
            query += " AND EXISTS (SELECT 1 FROM json_each(tags_json) WHERE value = ?)"
            params.append(tag)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_literature_search(search_id):
    """Return a single search by ID with parsed JSON fields."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM literature_searches WHERE id = ?", (search_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_literature_search(search_id, results=None, tags=None):
    """Update results (for refresh) or tags (for user edit). Updates updated_at."""
    conn = get_connection()
    try:
        now = datetime.utcnow().isoformat()

        if results is not None:
            # Fetch source_type to compute result_count
            row = conn.execute(
                "SELECT source_type FROM literature_searches WHERE id = ?",
                (search_id,),
            ).fetchone()
            if row is None:
                return
            result_count = _compute_result_count(row["source_type"], results)
            conn.execute(
                """UPDATE literature_searches SET
                       results_json = ?, result_count = ?, updated_at = ?
                   WHERE id = ?""",
                (json.dumps(results), result_count, now, search_id),
            )

        if tags is not None:
            conn.execute(
                "UPDATE literature_searches SET tags_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(tags), now, search_id),
            )

        conn.commit()
    finally:
        conn.close()


def delete_literature_search(search_id):
    """Delete a saved search by ID."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM literature_searches WHERE id = ?", (search_id,))
        conn.commit()
    finally:
        conn.close()


def get_all_literature_tags():
    """Return a sorted list of unique tags across all saved searches."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT value FROM literature_searches, json_each(tags_json) ORDER BY value"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def get_stats():
    """Return summary statistics for the dashboard."""
    conn = get_connection()
    try:
        total_proteins = conn.execute(
            "SELECT COUNT(*) FROM proteins"
        ).fetchone()[0]
        total_compounds = conn.execute(
            "SELECT COUNT(*) FROM compounds"
        ).fetchone()[0]
        total_runs = conn.execute(
            "SELECT COUNT(*) FROM docking_runs"
        ).fetchone()[0]

        best_row = conn.execute(
            """SELECT dr.best_energy, c.name AS compound_name
               FROM docking_runs dr
               JOIN compounds c ON dr.compound_id = c.id
               ORDER BY dr.best_energy ASC
               LIMIT 1"""
        ).fetchone()

        best_energy = best_row["best_energy"] if best_row else None
        best_compound = best_row["compound_name"] if best_row else None

        return {
            "total_proteins": total_proteins,
            "total_compounds": total_compounds,
            "total_runs": total_runs,
            "best_energy": best_energy,
            "best_compound": best_compound,
        }
    finally:
        conn.close()
