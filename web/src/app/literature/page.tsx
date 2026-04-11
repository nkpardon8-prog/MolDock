'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import { apiGet, apiPost, apiDelete } from '@/lib/api'
import type { LiteratureSearch } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Slider } from '@/components/ui/slider'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { MetricCard } from '@/components/metric-card'
import {
  Search,
  RefreshCw,
  Trash2,
  Eye,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FlaskConical,
  Loader2,
} from 'lucide-react'

type SourceType = 'pubmed' | 'chembl' | 'uniprot' | 'perplexity'

interface SearchState {
  loading: boolean
  error: string | null
  results: Record<string, unknown>[] | null
  sourceType: SourceType | null
}

const SOURCE_COLORS: Record<SourceType, string> = {
  pubmed: 'bg-blue-600/20 text-blue-400',
  chembl: 'bg-purple-600/20 text-purple-400',
  uniprot: 'bg-amber-600/20 text-amber-400',
  perplexity: 'bg-green-600/20 text-green-400',
}

export default function LiteraturePage() {
  const router = useRouter()
  const [savedSearches, setSavedSearches] = useState<LiteratureSearch[]>([])
  const [savedOpen, setSavedOpen] = useState(true)
  const [savedLoading, setSavedLoading] = useState(true)
  const [expandedArticles, setExpandedArticles] = useState<Set<string>>(new Set())
  const [expandedDiseases, setExpandedDiseases] = useState(false)

  const [searchState, setSearchState] = useState<SearchState>({
    loading: false,
    error: null,
    results: null,
    sourceType: null,
  })

  // PubMed state
  const [pubmedQuery, setPubmedQuery] = useState('')
  const [pubmedMax, setPubmedMax] = useState(10)

  // ChEMBL state
  const [chemblQuery, setChemblQuery] = useState('')

  // UniProt state
  const [uniprotMode, setUniprotMode] = useState<'name' | 'id'>('name')
  const [uniprotQuery, setUniprotQuery] = useState('')

  // Perplexity state
  const [perplexityQuery, setPerplexityQuery] = useState('')
  const [perplexityTimeframe, setPerplexityTimeframe] = useState<'all' | 'recent'>('all')

  // Expanded sources for perplexity
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set())

  const fetchSaved = useCallback(async () => {
    setSavedLoading(true)
    try {
      const data = await apiGet<LiteratureSearch[]>('/api/literature/searches')
      setSavedSearches(data)
    } catch {
      // silent
    } finally {
      setSavedLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSaved()
  }, [fetchSaved])

  async function doSearch(source: SourceType, query: string, extras?: Record<string, unknown>) {
    setSearchState({ loading: true, error: null, results: null, sourceType: source })
    try {
      const body: Record<string, unknown> = { query, source_type: source, ...extras }
      const res = await apiPost<LiteratureSearch>('/api/literature/search', body)
      setSearchState({ loading: false, error: null, results: res.results, sourceType: source })
      fetchSaved()
    } catch (err) {
      setSearchState({
        loading: false,
        error: err instanceof Error ? err.message : 'Search failed',
        results: null,
        sourceType: source,
      })
    }
  }

  async function deleteSaved(id: string) {
    try {
      await apiDelete(`/api/literature/searches/${id}`)
      setSavedSearches((prev) => prev.filter((s) => s.id !== id))
    } catch {
      // silent
    }
  }

  function viewSaved(s: LiteratureSearch) {
    setSearchState({
      loading: false,
      error: null,
      results: s.results,
      sourceType: s.source_type as SourceType,
    })
  }

  async function refreshSaved(s: LiteratureSearch) {
    await doSearch(s.source_type as SourceType, s.query, {
      max_results: s.source_type === 'pubmed' ? 10 : undefined,
      timeframe: s.timeframe ?? undefined,
    })
  }

  function toggleArticle(id: string) {
    setExpandedArticles((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSource(idx: number) {
    setExpandedSources((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-bold text-[#FAFAFA]">Literature Search</h1>

      {/* Saved Searches */}
      <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
        <CardHeader>
          <CardTitle
            className="flex cursor-pointer items-center gap-2 text-[#FAFAFA]"
            onClick={() => setSavedOpen(!savedOpen)}
          >
            {savedOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
            Saved Searches
            <span className="text-sm font-normal text-[#8B949E]">
              ({savedSearches.length})
            </span>
          </CardTitle>
        </CardHeader>
        {savedOpen && (
          <CardContent>
            {savedLoading ? (
              <div className="flex items-center gap-2 text-[#8B949E]">
                <Loader2 className="size-4 animate-spin" />
                Loading...
              </div>
            ) : savedSearches.length === 0 ? (
              <p className="text-sm text-[#8B949E]">No saved searches yet.</p>
            ) : (
              <div className="space-y-2">
                {savedSearches.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center gap-3 rounded-md border border-[#2A2F3E] bg-[#0E1117] px-3 py-2"
                  >
                    <span
                      className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${SOURCE_COLORS[s.source_type as SourceType] ?? 'bg-zinc-700 text-zinc-300'}`}
                    >
                      {s.source_type}
                    </span>
                    <span className="flex-1 truncate text-sm text-[#FAFAFA]">
                      {s.query}
                    </span>
                    <span className="text-xs text-[#8B949E]">
                      {s.results?.length ?? 0} results
                    </span>
                    <span className="text-xs text-[#8B949E]">
                      {s.created_at ? new Date(s.created_at).toLocaleDateString() : ''}
                    </span>
                    <Button variant="ghost" size="icon-xs" onClick={() => viewSaved(s)}>
                      <Eye className="size-3" />
                    </Button>
                    <Button variant="ghost" size="icon-xs" onClick={() => refreshSaved(s)}>
                      <RefreshCw className="size-3" />
                    </Button>
                    <Button variant="ghost" size="icon-xs" onClick={() => deleteSaved(s.id)}>
                      <Trash2 className="size-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        )}
      </Card>

      {/* Search Tabs */}
      <Tabs defaultValue="pubmed">
        <TabsList className="w-full">
          <TabsTrigger value="pubmed">PubMed</TabsTrigger>
          <TabsTrigger value="chembl">ChEMBL</TabsTrigger>
          <TabsTrigger value="uniprot">UniProt</TabsTrigger>
          <TabsTrigger value="perplexity">AI Research</TabsTrigger>
        </TabsList>

        {/* PubMed Tab */}
        <TabsContent value="pubmed">
          <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
            <CardContent className="space-y-4 pt-4">
              <div className="space-y-2">
                <Label className="text-[#FAFAFA]">Search Query</Label>
                <Input
                  placeholder="e.g. BACE1 marine natural products"
                  value={pubmedQuery}
                  onChange={(e) => setPubmedQuery(e.target.value)}
                  className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && pubmedQuery.trim()) {
                      doSearch('pubmed', pubmedQuery, { max_results: pubmedMax })
                    }
                  }}
                />
              </div>
              <div className="space-y-2">
                <Label className="text-[#FAFAFA]">Max Results: {pubmedMax}</Label>
                <Slider
                  min={5}
                  max={50}
                  value={[pubmedMax]}
                  onValueChange={(val) => {
                    const arr = Array.isArray(val) ? val : [val]
                    setPubmedMax(arr[0])
                  }}
                />
              </div>
              <Button
                className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
                disabled={!pubmedQuery.trim() || searchState.loading}
                onClick={() => doSearch('pubmed', pubmedQuery, { max_results: pubmedMax })}
              >
                {searchState.loading && searchState.sourceType === 'pubmed' ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <Search className="mr-2 size-4" />
                )}
                Search PubMed
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ChEMBL Tab */}
        <TabsContent value="chembl">
          <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
            <CardContent className="space-y-4 pt-4">
              <div className="space-y-2">
                <Label className="text-[#FAFAFA]">Target Name</Label>
                <Input
                  placeholder="e.g. Aromatase"
                  value={chemblQuery}
                  onChange={(e) => setChemblQuery(e.target.value)}
                  className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && chemblQuery.trim()) {
                      doSearch('chembl', chemblQuery)
                    }
                  }}
                />
              </div>
              <Button
                className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
                disabled={!chemblQuery.trim() || searchState.loading}
                onClick={() => doSearch('chembl', chemblQuery)}
              >
                {searchState.loading && searchState.sourceType === 'chembl' ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <Search className="mr-2 size-4" />
                )}
                Search ChEMBL
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* UniProt Tab */}
        <TabsContent value="uniprot">
          <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
            <CardContent className="space-y-4 pt-4">
              <div className="flex gap-4">
                <label className="flex items-center gap-2 text-sm text-[#FAFAFA]">
                  <input
                    type="radio"
                    name="uniprot-mode"
                    checked={uniprotMode === 'name'}
                    onChange={() => setUniprotMode('name')}
                    className="accent-[#00D4AA]"
                  />
                  Protein name
                </label>
                <label className="flex items-center gap-2 text-sm text-[#FAFAFA]">
                  <input
                    type="radio"
                    name="uniprot-mode"
                    checked={uniprotMode === 'id'}
                    onChange={() => setUniprotMode('id')}
                    className="accent-[#00D4AA]"
                  />
                  UniProt ID
                </label>
              </div>
              <div className="space-y-2">
                <Label className="text-[#FAFAFA]">
                  {uniprotMode === 'name' ? 'Protein Name' : 'UniProt ID'}
                </Label>
                <Input
                  placeholder={uniprotMode === 'name' ? 'e.g. HIF-2 alpha' : 'e.g. Q99814'}
                  value={uniprotQuery}
                  onChange={(e) => setUniprotQuery(e.target.value)}
                  className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && uniprotQuery.trim()) {
                      doSearch('uniprot', uniprotQuery)
                    }
                  }}
                />
              </div>
              <Button
                className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
                disabled={!uniprotQuery.trim() || searchState.loading}
                onClick={() => doSearch('uniprot', uniprotQuery)}
              >
                {searchState.loading && searchState.sourceType === 'uniprot' ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <Search className="mr-2 size-4" />
                )}
                Search UniProt
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Perplexity Tab */}
        <TabsContent value="perplexity">
          <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
            <CardContent className="space-y-4 pt-4">
              <div className="space-y-2">
                <Label className="text-[#FAFAFA]">Research Query</Label>
                <Input
                  placeholder="e.g. Recent advances in BACE1 inhibitors from marine sources"
                  value={perplexityQuery}
                  onChange={(e) => setPerplexityQuery(e.target.value)}
                  className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && perplexityQuery.trim()) {
                      doSearch('perplexity', perplexityQuery, { timeframe: perplexityTimeframe })
                    }
                  }}
                />
              </div>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 text-sm text-[#FAFAFA]">
                  <input
                    type="radio"
                    name="pplx-timeframe"
                    checked={perplexityTimeframe === 'all'}
                    onChange={() => setPerplexityTimeframe('all')}
                    className="accent-[#00D4AA]"
                  />
                  All time
                </label>
                <label className="flex items-center gap-2 text-sm text-[#FAFAFA]">
                  <input
                    type="radio"
                    name="pplx-timeframe"
                    checked={perplexityTimeframe === 'recent'}
                    onChange={() => setPerplexityTimeframe('recent')}
                    className="accent-[#00D4AA]"
                  />
                  Recent
                </label>
              </div>
              <Button
                className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
                disabled={!perplexityQuery.trim() || searchState.loading}
                onClick={() =>
                  doSearch('perplexity', perplexityQuery, { timeframe: perplexityTimeframe })
                }
              >
                {searchState.loading && searchState.sourceType === 'perplexity' ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <Search className="mr-2 size-4" />
                )}
                Search with AI
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Error display */}
      {searchState.error && (
        <div className="rounded-lg border border-red-500/50 bg-red-950/30 p-4">
          <p className="text-sm text-red-400">{searchState.error}</p>
        </div>
      )}

      {/* Loading */}
      {searchState.loading && (
        <div className="flex items-center gap-3 rounded-lg border border-[#2A2F3E] bg-[#1A1F2E] p-4">
          <Loader2 className="size-4 animate-spin text-[#00D4AA]" />
          <span className="text-sm text-[#8B949E]">Searching...</span>
        </div>
      )}

      {/* Results */}
      {searchState.results && !searchState.loading && (
        <ResultsDisplay
          results={searchState.results}
          sourceType={searchState.sourceType!}
          expandedArticles={expandedArticles}
          toggleArticle={toggleArticle}
          expandedDiseases={expandedDiseases}
          setExpandedDiseases={setExpandedDiseases}
          expandedSources={expandedSources}
          toggleSource={toggleSource}
          onDockCompound={(smiles, name) => {
            const params = new URLSearchParams()
            if (smiles) params.set('smiles', smiles)
            if (name) params.set('name', name)
            router.push(`/dock?${params.toString()}`)
          }}
        />
      )}
    </div>
  )
}

interface ResultsDisplayProps {
  results: Record<string, unknown>[]
  sourceType: SourceType
  expandedArticles: Set<string>
  toggleArticle: (id: string) => void
  expandedDiseases: boolean
  setExpandedDiseases: (v: boolean) => void
  expandedSources: Set<number>
  toggleSource: (idx: number) => void
  onDockCompound: (smiles: string, name: string) => void
}

function ResultsDisplay({
  results,
  sourceType,
  expandedArticles,
  toggleArticle,
  expandedDiseases,
  setExpandedDiseases,
  expandedSources,
  toggleSource,
  onDockCompound,
}: ResultsDisplayProps) {
  if (sourceType === 'pubmed') {
    return <PubMedResults results={results} expanded={expandedArticles} toggle={toggleArticle} />
  }
  if (sourceType === 'chembl') {
    return <ChemblResults results={results} onDock={onDockCompound} />
  }
  if (sourceType === 'uniprot') {
    return (
      <UniProtResults
        results={results}
        expandedDiseases={expandedDiseases}
        setExpandedDiseases={setExpandedDiseases}
      />
    )
  }
  if (sourceType === 'perplexity') {
    return (
      <PerplexityResults results={results} expandedSources={expandedSources} toggleSource={toggleSource} />
    )
  }
  return null
}

function PubMedResults({
  results,
  expanded,
  toggle,
}: {
  results: Record<string, unknown>[]
  expanded: Set<string>
  toggle: (id: string) => void
}) {
  if (results.length === 0) {
    return <p className="text-sm text-[#8B949E]">No results found.</p>
  }

  return (
    <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
      <CardHeader>
        <CardTitle className="text-[#FAFAFA]">
          PubMed Results ({results.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2A2F3E] text-left text-[#8B949E]">
                <th className="pb-2 pr-4">PMID</th>
                <th className="pb-2 pr-4">Title</th>
                <th className="pb-2 pr-4">Authors</th>
                <th className="pb-2 pr-4">Journal</th>
                <th className="pb-2">Year</th>
              </tr>
            </thead>
            <tbody>
              {results.map((article) => {
                const pmid = String(article.pmid ?? article.PMID ?? '')
                const title = String(article.title ?? '')
                const authors = String(article.authors ?? '')
                const journal = String(article.journal ?? '')
                const year = String(article.year ?? article.pub_date ?? '')
                const abstract = String(article.abstract ?? '')
                const doi = String(article.doi ?? '')
                const isOpen = expanded.has(pmid)

                return (
                  <tr key={pmid} className="border-b border-[#2A2F3E]/50">
                    <td className="py-2 pr-4 align-top">
                      <button
                        className="font-mono text-[#00D4AA] hover:underline"
                        onClick={() => toggle(pmid)}
                      >
                        {pmid}
                      </button>
                    </td>
                    <td className="py-2 pr-4 align-top">
                      <button
                        className="text-left text-[#FAFAFA] hover:text-[#00D4AA]"
                        onClick={() => toggle(pmid)}
                      >
                        {title}
                      </button>
                      {isOpen && (
                        <div className="mt-2 space-y-2 rounded border border-[#2A2F3E] bg-[#0E1117] p-3">
                          {abstract && (
                            <div>
                              <p className="text-xs font-semibold text-[#8B949E]">Abstract</p>
                              <p className="mt-1 text-xs text-[#FAFAFA]">{abstract}</p>
                            </div>
                          )}
                          <div className="flex gap-3">
                            {doi && (
                              <a
                                href={`https://doi.org/${doi}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-1 text-xs text-[#00D4AA] hover:underline"
                              >
                                DOI <ExternalLink className="size-3" />
                              </a>
                            )}
                            <a
                              href={`https://pubmed.ncbi.nlm.nih.gov/${pmid}/`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-1 text-xs text-[#00D4AA] hover:underline"
                            >
                              PubMed <ExternalLink className="size-3" />
                            </a>
                          </div>
                        </div>
                      )}
                    </td>
                    <td className="py-2 pr-4 align-top text-[#8B949E]">{authors}</td>
                    <td className="py-2 pr-4 align-top text-[#8B949E]">{journal}</td>
                    <td className="py-2 align-top text-[#8B949E]">{year}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

function ChemblResults({
  results,
  onDock,
}: {
  results: Record<string, unknown>[]
  onDock: (smiles: string, name: string) => void
}) {
  if (results.length === 0) {
    return <p className="text-sm text-[#8B949E]">No results found.</p>
  }

  const first = results[0]
  const targetName = String(first.target_name ?? first.name ?? 'Unknown Target')
  const chemblId = String(first.target_chembl_id ?? first.chembl_id ?? '')

  return (
    <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
      <CardHeader>
        <CardTitle className="text-[#FAFAFA]">
          {targetName}
          {chemblId && (
            <Badge variant="secondary" className="ml-2">
              {chemblId}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2A2F3E] text-left text-[#8B949E]">
                <th className="pb-2 pr-4">Name</th>
                <th className="pb-2 pr-4">SMILES</th>
                <th className="pb-2 pr-4">Activity Type</th>
                <th className="pb-2 pr-4">Value</th>
                <th className="pb-2 pr-4">Units</th>
                <th className="pb-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {results.map((compound, idx) => {
                const name = String(compound.compound_name ?? compound.name ?? `Compound ${idx + 1}`)
                const smiles = String(compound.smiles ?? compound.canonical_smiles ?? '')
                const actType = String(compound.activity_type ?? compound.standard_type ?? '')
                const actValue = String(compound.activity_value ?? compound.standard_value ?? '')
                const units = String(compound.units ?? compound.standard_units ?? '')

                return (
                  <tr key={idx} className="border-b border-[#2A2F3E]/50">
                    <td className="py-2 pr-4 text-[#FAFAFA]">{name}</td>
                    <td className="max-w-[200px] truncate py-2 pr-4 font-mono text-xs text-[#8B949E]">
                      {smiles}
                    </td>
                    <td className="py-2 pr-4 text-[#8B949E]">{actType}</td>
                    <td className="py-2 pr-4 text-[#8B949E]">{actValue}</td>
                    <td className="py-2 pr-4 text-[#8B949E]">{units}</td>
                    <td className="py-2">
                      {smiles && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-[#00D4AA] hover:text-[#00D4AA]/80"
                          onClick={() => onDock(smiles, name)}
                        >
                          <FlaskConical className="mr-1 size-3" />
                          Dock this
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

function UniProtResults({
  results,
  expandedDiseases,
  setExpandedDiseases,
}: {
  results: Record<string, unknown>[]
  expandedDiseases: boolean
  setExpandedDiseases: (v: boolean) => void
}) {
  if (results.length === 0) {
    return <p className="text-sm text-[#8B949E]">No results found.</p>
  }

  const protein = results[0]
  const name = String(protein.protein_name ?? protein.name ?? 'Unknown Protein')
  const organism = String(protein.organism ?? '')
  const seqLength = String(protein.sequence_length ?? protein.length ?? '')
  const pdbStructures = (protein.pdb_structures ?? protein.structures ?? []) as Record<string, unknown>[]
  const functionText = String(protein.function ?? protein.function_text ?? '')
  const subcellular = String(protein.subcellular_location ?? '')
  const domains = (protein.domains ?? []) as string[]
  const diseases = (protein.diseases ?? []) as string[]

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-[#FAFAFA]">{name}</h3>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard label="Organism" value={organism || 'N/A'} />
        <MetricCard label="Sequence Length" value={seqLength || 'N/A'} />
        <MetricCard label="PDB Structures" value={pdbStructures.length} />
      </div>

      {functionText && (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardHeader>
            <CardTitle className="text-sm text-[#FAFAFA]">Function</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[#8B949E]">{functionText}</p>
          </CardContent>
        </Card>
      )}

      {subcellular && (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardHeader>
            <CardTitle className="text-sm text-[#FAFAFA]">Subcellular Location</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[#8B949E]">{subcellular}</p>
          </CardContent>
        </Card>
      )}

      {domains.length > 0 && (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardHeader>
            <CardTitle className="text-sm text-[#FAFAFA]">Domains</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {domains.map((d, i) => (
                <Badge key={i} variant="secondary">
                  {String(d)}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {diseases.length > 0 && (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardHeader>
            <CardTitle
              className="flex cursor-pointer items-center gap-2 text-sm text-[#FAFAFA]"
              onClick={() => setExpandedDiseases(!expandedDiseases)}
            >
              {expandedDiseases ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
              Diseases ({diseases.length})
            </CardTitle>
          </CardHeader>
          {expandedDiseases && (
            <CardContent>
              <ul className="list-inside list-disc space-y-1 text-sm text-[#8B949E]">
                {diseases.map((d, i) => (
                  <li key={i}>{String(d)}</li>
                ))}
              </ul>
            </CardContent>
          )}
        </Card>
      )}

      {pdbStructures.length > 0 && (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardHeader>
            <CardTitle className="text-sm text-[#FAFAFA]">PDB Structures</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
              {pdbStructures.map((pdb, i) => {
                const pdbId = String(pdb.pdb_id ?? pdb.id ?? pdb)
                return (
                  <a
                    key={i}
                    href={`https://www.rcsb.org/structure/${pdbId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 rounded border border-[#2A2F3E] bg-[#0E1117] px-3 py-2 text-sm text-[#00D4AA] hover:border-[#00D4AA]/50"
                  >
                    {pdbId}
                    <ExternalLink className="size-3" />
                  </a>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function PerplexityResults({
  results,
  expandedSources,
  toggleSource,
}: {
  results: Record<string, unknown>[]
  expandedSources: Set<number>
  toggleSource: (idx: number) => void
}) {
  if (results.length === 0) {
    return <p className="text-sm text-[#8B949E]">No results found.</p>
  }

  const data = results[0]
  const summary = String(data.summary ?? data.answer ?? data.text ?? '')
  const sources = (data.sources ?? data.citations ?? []) as Record<string, unknown>[]

  return (
    <div className="space-y-4">
      {summary && (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardHeader>
            <CardTitle className="text-[#FAFAFA]">AI Research Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="prose prose-sm prose-invert max-w-none">
              <ReactMarkdown>{summary}</ReactMarkdown>
            </div>
          </CardContent>
        </Card>
      )}

      {sources.length > 0 && (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardHeader>
            <CardTitle className="text-[#FAFAFA]">Sources ({sources.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {sources.map((source, idx) => {
                const title = String(source.title ?? source.name ?? `Source ${idx + 1}`)
                const url = String(source.url ?? source.link ?? '')
                const snippet = String(source.snippet ?? source.text ?? '')
                const isOpen = expandedSources.has(idx)

                return (
                  <div key={idx} className="rounded border border-[#2A2F3E] bg-[#0E1117] p-3">
                    <div className="flex items-center gap-2">
                      <button
                        className="flex-1 text-left text-sm text-[#FAFAFA] hover:text-[#00D4AA]"
                        onClick={() => toggleSource(idx)}
                      >
                        {isOpen ? (
                          <ChevronDown className="mr-1 inline size-3" />
                        ) : (
                          <ChevronRight className="mr-1 inline size-3" />
                        )}
                        {title}
                      </button>
                      {url && (
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[#00D4AA]"
                        >
                          <ExternalLink className="size-3" />
                        </a>
                      )}
                    </div>
                    {isOpen && snippet && (
                      <p className="mt-2 text-xs text-[#8B949E]">{snippet}</p>
                    )}
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
