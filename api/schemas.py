from pydantic import BaseModel, Field
from typing import Any, Generic, Optional, TypeVar
from datetime import datetime


T = TypeVar("T")


# ---------------------------------------------------------------------------
# Generic paginated wrapper
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Docking
# ---------------------------------------------------------------------------

class DockRequest(BaseModel):
    pdb_id: str
    compound_input: str
    exhaustiveness: int = Field(32, ge=8, le=64)


class DockingRunResponse(BaseModel):
    id: str
    protein_id: str
    compound_id: str
    best_energy: Optional[float] = None
    exhaustiveness: Optional[int] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# ADMET
# ---------------------------------------------------------------------------

class AdmetRequest(BaseModel):
    smiles: str


class AdmetResponse(BaseModel):
    smiles: str
    valid: bool
    lipinski: Optional[dict[str, Any]] = None
    veber: Optional[dict[str, Any]] = None
    mw: Optional[float] = None
    logp: Optional[float] = None
    hbd: Optional[int] = None
    hba: Optional[int] = None
    rotatable_bonds: Optional[int] = None
    tpsa: Optional[float] = None
    num_rings: Optional[int] = None
    num_aromatic_rings: Optional[int] = None
    fraction_csp3: Optional[float] = None
    molar_refractivity: Optional[float] = None
    num_heavy_atoms: Optional[int] = None
    sa_score: Optional[float] = None
    synthetic_assessment: Optional[str] = None
    drug_likeness_score: Optional[float] = None
    assessment: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class JobResponse(BaseModel):
    job_id: str
    status: str


# ---------------------------------------------------------------------------
# Proteins
# ---------------------------------------------------------------------------

class ProteinResponse(BaseModel):
    id: str
    pdb_id: str
    title: Optional[str] = None
    organism: Optional[str] = None
    resolution: Optional[float] = None
    method: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Compounds
# ---------------------------------------------------------------------------

class CompoundResponse(BaseModel):
    id: str
    name: Optional[str] = None
    smiles: Optional[str] = None
    cid: Optional[str] = None
    drug_likeness_score: Optional[float] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Literature
# ---------------------------------------------------------------------------

class LiteratureSearchRequest(BaseModel):
    query: str
    source_type: str
    max_results: int = Field(10, ge=1, le=100)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    project_name: str
    output_format: str
    results_dir: Optional[str] = None


# ---------------------------------------------------------------------------
# Optimize
# ---------------------------------------------------------------------------

class OptimizeRequest(BaseModel):
    smiles: Optional[str] = None
    compound: Optional[str] = None
    property_name: Optional[str] = None
    num_molecules: int = Field(10, ge=1, le=50)
    min_similarity: float = Field(0.3, ge=0.0, le=1.0)
    scaled_radius: float = Field(1.0, ge=0.1, le=5.0)


# ---------------------------------------------------------------------------
# Chat streaming
# ---------------------------------------------------------------------------

class ChatStreamEvent(BaseModel):
    event: str
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Protein fetch
# ---------------------------------------------------------------------------

class FetchProteinRequest(BaseModel):
    pdb_id: str = Field(..., min_length=4, max_length=4)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    max_results: int = Field(10, ge=1, le=100)


# ---------------------------------------------------------------------------
# Literature tags
# ---------------------------------------------------------------------------

class UpdateLiteratureTagsRequest(BaseModel):
    tags: list[str]


# ---------------------------------------------------------------------------
# NP Atlas search
# ---------------------------------------------------------------------------

class NpAtlasSearchRequest(BaseModel):
    query: str
    search_type: str = "name"
    max_results: int = Field(20, ge=1, le=100)
