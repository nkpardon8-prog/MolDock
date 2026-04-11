export interface Protein {
  id: string
  pdb_id: string
  title?: string | null
  organism?: string | null
  resolution?: number | null
  method?: string | null
  pdb_path?: string | null
  pdbqt_path?: string | null
  binding_site?: Record<string, unknown> | null
  created_at?: string | null
}

export interface Compound {
  id: string
  name?: string | null
  smiles?: string | null
  cid?: string | null
  drug_likeness_score?: number | null
  admet?: Record<string, unknown> | null
  created_at?: string | null
}

export interface DockingRun {
  id: string
  protein_id: string
  compound_id: string
  best_energy?: number | null
  all_energies?: number[] | null
  exhaustiveness?: number | null
  center_x?: number | null
  center_y?: number | null
  center_z?: number | null
  size_x?: number | null
  size_y?: number | null
  size_z?: number | null
  output_path?: string | null
  interactions?: Record<string, unknown> | null
  created_at?: string | null
  proteins?: { pdb_id: string }
  compounds?: { name: string }
}

export interface AdmetResult {
  smiles: string
  valid: boolean
  lipinski?: Record<string, unknown> | null
  veber?: Record<string, unknown> | null
  mw?: number | null
  logp?: number | null
  hbd?: number | null
  hba?: number | null
  rotatable_bonds?: number | null
  tpsa?: number | null
  num_rings?: number | null
  num_aromatic_rings?: number | null
  fraction_csp3?: number | null
  molar_refractivity?: number | null
  num_heavy_atoms?: number | null
  sa_score?: number | null
  synthetic_assessment?: string | null
  drug_likeness_score?: number | null
  assessment?: string | null
}

export interface ChatSession {
  id: string
  user_id: string
  title?: string | null
  created_at?: string | null
}

export interface ChatMessage {
  id: string
  session_id: string
  role: string
  content: string
  artifacts?: Record<string, unknown> | null
  created_at?: string | null
}

export interface Job {
  id: string
  user_id: string
  job_type: string
  status: string
  input_data?: Record<string, unknown> | null
  result?: Record<string, unknown> | null
  error?: string | null
  created_at?: string | null
}

export interface StatsResponse {
  total_proteins: number
  total_compounds: number
  total_runs: number
  best_energy?: number | null
}

export interface PaginatedResponse<T> {
  items: T[]
  total?: number
  limit: number
  offset: number
}

export interface JobStreamEvent {
  event: string
  payload: Record<string, unknown>
}

export interface LiteratureSearch {
  id: string
  user_id: string
  query: string
  source_type: string
  results: Record<string, unknown>[]
  tags?: string[] | null
  timeframe?: string | null
  created_at?: string | null
}
