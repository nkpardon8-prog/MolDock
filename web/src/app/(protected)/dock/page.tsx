'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import dynamic from 'next/dynamic'
import { apiPost } from '@/lib/api'
import { useJobStream } from '@/components/jobs/use-job-stream'
import { JobProgress } from '@/components/jobs/job-progress'
import { MetricCard } from '@/components/metric-card'
import { FilePanel } from '@/components/file-panel'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { FlaskConical, ChevronDown, ChevronRight, ExternalLink, Search, X } from 'lucide-react'

const AdmetRadar = dynamic(
  () => import('@/components/charts/admet-radar').then((m) => ({ default: m.AdmetRadar })),
  { ssr: false },
)

const EnergyBarChart = dynamic(
  () => import('@/components/charts/energy-bar-chart').then((m) => ({ default: m.EnergyBarChart })),
  { ssr: false },
)

function bindingQuality(energy: number): { label: string; color: string } {
  if (energy <= -9.0) return { label: 'Excellent', color: '#00D4AA' }
  if (energy <= -7.0) return { label: 'Strong', color: '#4ECDC4' }
  if (energy <= -5.0) return { label: 'Moderate', color: '#FFD700' }
  return { label: 'Weak', color: '#FF4B4B' }
}

export default function DockPage() {
  const [pdbId, setPdbId] = useState('')
  const [proteinQuery, setProteinQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Array<{ pdb_id: string; title: string; organism?: string; resolution?: number; method?: string }>>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [showDropdown, setShowDropdown] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const [compound, setCompound] = useState('')
  const [exhaustiveness, setExhaustiveness] = useState(32)
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [proteinInfoOpen, setProteinInfoOpen] = useState(true)
  const [bindingSiteOpen, setBindingSiteOpen] = useState(true)

  const { status, progress, result, error } = useJobStream(jobId)

  const resultData = result as Record<string, unknown> | null
  const bestEnergy = resultData?.best_energy as number | undefined
  const allEnergies = resultData?.all_energies as number[] | undefined
  const nPoses = resultData?.n_poses as number | undefined
  const admet = resultData?.admet as Record<string, unknown> | undefined
  const drugLikenessScore = (resultData?.drug_likeness_score ?? admet?.drug_likeness_score) as number | undefined
  const saScore = (resultData?.sa_score ?? admet?.sa_score) as number | undefined
  const saAssessment = (resultData?.sa_assessment ?? admet?.synthetic_assessment) as string | undefined
  const outputPath = resultData?.output_path as string | undefined
  const receptorPath = resultData?.receptor_path as string | undefined
  const ligandPath = resultData?.ligand_path as string | undefined
  const compoundName = resultData?.compound as string | undefined
  const proteinName = resultData?.protein as string | undefined
  const runId = resultData?.run_id as string | undefined
  const proteinInfo = resultData?.protein_info as Record<string, unknown> | undefined
  const bindingSite = resultData?.binding_site as Record<string, unknown> | undefined
  const allPoses = resultData?.all_poses as Array<{affinity: number, rmsd_lb: number, rmsd_ub: number}> | undefined
  const smiles = resultData?.smiles as string | undefined
  const compoundCid = resultData?.compound_cid as number | undefined
  const iupacName = resultData?.iupac_name as string | undefined
  const formula = resultData?.formula as string | undefined

  const isPdbId = (s: string) => /^[A-Za-z0-9]{4}$/.test(s.trim())

  const handleProteinInput = useCallback((value: string) => {
    setProteinQuery(value)
    if (isPdbId(value)) {
      setPdbId(value.trim().toUpperCase())
      setShowDropdown(false)
      setSearchResults([])
    } else {
      setPdbId('')
    }
  }, [])

  useEffect(() => {
    if (isPdbId(proteinQuery) || proteinQuery.trim().length < 2) {
      setSearchResults([])
      setShowDropdown(false)
      return
    }

    const timer = setTimeout(async () => {
      setSearchLoading(true)
      try {
        const res = await apiPost<{ results: Array<{ pdb_id: string; title: string; organism?: string; resolution?: number; method?: string }> }>('/api/proteins/search', {
          query: proteinQuery.trim(),
          max_results: 8,
        })
        setSearchResults(res.results)
        setShowDropdown(res.results.length > 0)
      } catch {
        setSearchResults([])
      } finally {
        setSearchLoading(false)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [proteinQuery])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelectProtein = useCallback((result: { pdb_id: string; title: string }) => {
    setPdbId(result.pdb_id)
    setProteinQuery(`${result.pdb_id} \u2014 ${result.title}`)
    setShowDropdown(false)
    setSearchResults([])
  }, [])

  const handleSubmit = useCallback(async () => {
    if (!pdbId.trim() || !compound.trim()) return

    setSubmitError(null)
    setSubmitting(true)
    setJobId(null)

    try {
      const res = await apiPost<{ job_id: string; status: string }>('/api/dock/', {
        pdb_id: pdbId.trim().toUpperCase(),
        compound_input: compound.trim(),
        exhaustiveness,
      })
      setJobId(res.job_id)
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to submit docking job')
    } finally {
      setSubmitting(false)
    }
  }, [pdbId, compound, exhaustiveness])

  const isRunning = submitting || status === 'connecting' || status === 'streaming'
  const quality = bestEnergy != null ? bindingQuality(bestEnergy) : null

  const files = runId ? [
    ...(outputPath ? [{
      name: outputPath.split('/').pop() || 'docked.pdbqt',
      type: 'docked' as const,
      downloadUrl: `/api/results/${runId}/file`,
      path: outputPath,
    }] : []),
    ...(receptorPath ? [{
      name: receptorPath.split('/').pop() || 'receptor.pdbqt',
      type: 'receptor' as const,
      downloadUrl: `/api/proteins/${proteinName}/file`,
      path: receptorPath,
    }] : []),
    ...(ligandPath ? [{
      name: ligandPath.split('/').pop() || 'ligand.pdbqt',
      type: 'ligand' as const,
      downloadUrl: `/api/results/${runId}/file`,
      path: ligandPath,
    }] : []),
  ] : []

  return (
    <div className="flex flex-col gap-6 p-6">
      <h1 className="text-xl font-bold text-[#FAFAFA]">Molecular Docking</h1>

      <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
        <CardHeader>
          <CardTitle className="text-[#FAFAFA]">Docking Parameters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="pdb-id" className="text-[#FAFAFA]">
                Protein <span className="text-[#8B949E] font-normal text-xs">(PDB ID or name)</span>
              </Label>
              <div className="relative" ref={dropdownRef}>
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-[#8B949E]" />
                  <Input
                    id="pdb-id"
                    placeholder="e.g. 3S7S or aromatase"
                    value={proteinQuery}
                    onChange={(e) => handleProteinInput(e.target.value)}
                    disabled={isRunning}
                    className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA] pl-8 pr-8"
                  />
                  {searchLoading && (
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2">
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#8B949E] border-t-[#00D4AA]" />
                    </div>
                  )}
                  {!searchLoading && pdbId && proteinQuery.length > 4 && (
                    <button
                      type="button"
                      onClick={() => { setProteinQuery(''); setPdbId(''); setSearchResults([]); }}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#8B949E] hover:text-[#FAFAFA]"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
                {pdbId && proteinQuery !== pdbId && (
                  <p className="mt-1 text-xs text-[#00D4AA] font-mono">PDB: {pdbId}</p>
                )}
                {!pdbId && proteinQuery.trim().length >= 2 && !showDropdown && !searchLoading && searchResults.length === 0 && (
                  <p className="mt-1 text-xs text-[#8B949E]">No results found. Try a different name or enter a 4-character PDB ID directly.</p>
                )}
                {!pdbId && proteinQuery.trim().length >= 2 && !showDropdown && !searchLoading && searchResults.length > 0 && (
                  <p className="mt-1 text-xs text-amber-400">Select a protein from the results above</p>
                )}
                {showDropdown && searchResults.length > 0 && (
                  <div className="absolute z-50 mt-1 w-full rounded-lg border border-[#2A2F3E] bg-[#1A1F2E] shadow-xl max-h-64 overflow-auto">
                    {searchResults.map((r) => (
                      <button
                        key={r.pdb_id}
                        type="button"
                        onClick={() => handleSelectProtein(r)}
                        className="w-full px-3 py-2 text-left hover:bg-[#2A2F3E] transition-colors border-b border-[#2A2F3E]/50 last:border-0"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm text-[#00D4AA] font-semibold">{r.pdb_id}</span>
                          {r.resolution != null && (
                            <span className="text-[10px] text-[#8B949E]">{Number(r.resolution).toFixed(1)}A</span>
                          )}
                        </div>
                        <p className="text-xs text-[#FAFAFA] truncate">{r.title}</p>
                        {r.organism && (
                          <p className="text-[10px] text-[#8B949E] italic truncate">{r.organism}</p>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="compound" className="text-[#FAFAFA]">Compound (name or SMILES)</Label>
              <Input
                id="compound"
                placeholder="e.g. aspirin or CC(=O)Oc1ccccc1C(=O)O"
                value={compound}
                onChange={(e) => setCompound(e.target.value)}
                disabled={isRunning}
                className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
              />
            </div>

            <div className="space-y-2 sm:col-span-2">
              <Label className="text-[#FAFAFA]">
                Exhaustiveness: <span className="font-mono text-[#00D4AA]">{exhaustiveness}</span>
              </Label>
              <Slider
                min={8}
                max={64}
                step={1}
                value={exhaustiveness}
                onValueChange={(val) => setExhaustiveness(val as number)}
                disabled={isRunning}
              />
              <div className="flex justify-between text-xs text-[#8B949E]">
                <span>8 (fast)</span>
                <span>64 (thorough)</span>
              </div>
            </div>
          </div>

          {submitError && (
            <div className="mt-4 rounded-lg border border-red-500/50 bg-red-950/30 p-3">
              <p className="text-sm text-red-400">{submitError}</p>
            </div>
          )}

          <Button
            className="mt-5 gap-2 bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
            disabled={isRunning || !pdbId.trim() || !compound.trim()}
            onClick={handleSubmit}
          >
            <FlaskConical className="size-4" />
            {submitting ? 'Submitting...' : 'Start Docking'}
          </Button>
        </CardContent>
      </Card>

      {(status === 'connecting' || status === 'streaming' || status === 'error') && (
        <JobProgress status={status} progress={progress} error={error} />
      )}

      {status === 'error' && error && (
        <div className="rounded-lg border border-red-500/50 bg-red-950/30 p-4">
          <p className="text-sm font-medium text-red-400">{error}</p>
        </div>
      )}

      {status === 'complete' && resultData && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <MetricCard
              label="Best Energy"
              value={bestEnergy != null ? `${bestEnergy.toFixed(1)} kcal/mol` : '--'}
              deltaColor={quality?.color}
            />
            <MetricCard
              label="Poses Found"
              value={nPoses ?? allEnergies?.length ?? '--'}
            />
            <MetricCard
              label="Binding Quality"
              value={quality?.label ?? '--'}
              deltaColor={quality?.color}
            />
            <MetricCard
              label="Drug-likeness"
              value={drugLikenessScore != null ? drugLikenessScore.toFixed(2) : '--'}
              delta={admet?.assessment as string | undefined}
              deltaColor={drugLikenessScore != null && drugLikenessScore >= 0.7 ? '#00D4AA' : '#FFD700'}
            />
            <MetricCard
              label="SA Score"
              value={saScore != null ? saScore.toFixed(1) : '--'}
              delta={saAssessment}
              deltaColor={saScore != null && saScore <= 3 ? '#00D4AA' : '#FFD700'}
            />
          </div>

          {proteinInfo && (
            <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
              <CardHeader
                className="cursor-pointer select-none"
                onClick={() => setProteinInfoOpen(!proteinInfoOpen)}
              >
                <div className="flex items-center gap-2">
                  {proteinInfoOpen
                    ? <ChevronDown className="h-4 w-4 text-[#8B949E]" />
                    : <ChevronRight className="h-4 w-4 text-[#8B949E]" />}
                  <CardTitle className="text-sm text-[#FAFAFA]">Protein Information</CardTitle>
                </div>
              </CardHeader>
              {proteinInfoOpen && (
                <CardContent>
                  {proteinInfo.title != null && (
                    <h3 className="mb-3 text-sm font-semibold text-[#FAFAFA]">{String(proteinInfo.title)}</h3>
                  )}
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {proteinInfo.organism != null && (
                      <div>
                        <p className="text-xs text-[#8B949E]">Organism</p>
                        <p className="text-sm text-[#FAFAFA]">{String(proteinInfo.organism)}</p>
                      </div>
                    )}
                    {proteinInfo.resolution != null && (
                      <div>
                        <p className="text-xs text-[#8B949E]">Resolution</p>
                        <p className="text-sm font-mono text-[#FAFAFA]">{Number(proteinInfo.resolution).toFixed(2)} A</p>
                      </div>
                    )}
                    {proteinInfo.method != null && (
                      <div>
                        <p className="text-xs text-[#8B949E]">Method</p>
                        <p className="text-sm text-[#FAFAFA]">{String(proteinInfo.method)}</p>
                      </div>
                    )}
                    {Array.isArray(proteinInfo.chains) && (
                      <div>
                        <p className="text-xs text-[#8B949E]">Chains</p>
                        <p className="text-sm text-[#FAFAFA]">{proteinInfo.chains.length}</p>
                      </div>
                    )}
                  </div>
                  {Array.isArray(proteinInfo.ligands) && proteinInfo.ligands.length > 0 && (
                    <div className="mt-3">
                      <p className="mb-1.5 text-xs text-[#8B949E]">Co-crystallized Ligands</p>
                      <div className="flex flex-wrap gap-1.5">
                        {proteinInfo.ligands.map((lig, i) => (
                          <Badge key={i} variant="secondary" className="bg-[#00D4AA]/15 text-[#00D4AA] border border-[#00D4AA]/30">
                            {String(lig)}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {proteinInfo.citation != null && typeof proteinInfo.citation === 'object' && (
                    <div className="mt-3 rounded border border-[#2A2F3E] bg-[#0E1117] p-2.5">
                      <p className="text-xs text-[#8B949E]">Citation</p>
                      <p className="mt-0.5 text-sm text-[#FAFAFA]">
                        {(proteinInfo.citation as Record<string, unknown>).title != null ? String((proteinInfo.citation as Record<string, unknown>).title) : null}
                        {(proteinInfo.citation as Record<string, unknown>).journal != null ? (
                          <>, <span className="italic">{String((proteinInfo.citation as Record<string, unknown>).journal)}</span></>
                        ) : null}
                        {(proteinInfo.citation as Record<string, unknown>).year != null ? (
                          <> ({String((proteinInfo.citation as Record<string, unknown>).year)})</>
                        ) : null}
                      </p>
                      {(proteinInfo.citation as Record<string, unknown>).doi != null && (
                        <a
                          href={`https://doi.org/${String((proteinInfo.citation as Record<string, unknown>).doi)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-1 inline-flex items-center gap-1 text-xs text-[#00D4AA] hover:underline"
                        >
                          <ExternalLink className="h-3 w-3" />
                          DOI: {String((proteinInfo.citation as Record<string, unknown>).doi)}
                        </a>
                      )}
                    </div>
                  )}
                </CardContent>
              )}
            </Card>
          )}

          {bindingSite && (
            <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
              <CardHeader
                className="cursor-pointer select-none"
                onClick={() => setBindingSiteOpen(!bindingSiteOpen)}
              >
                <div className="flex items-center gap-2">
                  {bindingSiteOpen
                    ? <ChevronDown className="h-4 w-4 text-[#8B949E]" />
                    : <ChevronRight className="h-4 w-4 text-[#8B949E]" />}
                  <CardTitle className="text-sm text-[#FAFAFA]">Binding Site</CardTitle>
                </div>
              </CardHeader>
              {bindingSiteOpen && (
                <CardContent>
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    <div>
                      <p className="text-xs text-[#8B949E]">Center (X, Y, Z)</p>
                      <p className="text-sm font-mono text-[#FAFAFA]">
                        {bindingSite.center_x != null ? Number(bindingSite.center_x).toFixed(1) : '--'},{' '}
                        {bindingSite.center_y != null ? Number(bindingSite.center_y).toFixed(1) : '--'},{' '}
                        {bindingSite.center_z != null ? Number(bindingSite.center_z).toFixed(1) : '--'}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-[#8B949E]">Box Size (X, Y, Z)</p>
                      <p className="text-sm font-mono text-[#FAFAFA]">
                        {bindingSite.size_x != null ? Number(bindingSite.size_x).toFixed(1) : '--'},{' '}
                        {bindingSite.size_y != null ? Number(bindingSite.size_y).toFixed(1) : '--'},{' '}
                        {bindingSite.size_z != null ? Number(bindingSite.size_z).toFixed(1) : '--'}
                      </p>
                    </div>
                    <div className="sm:col-span-2">
                      <p className="text-xs text-[#8B949E]">Detected Ligand</p>
                      <div className="mt-1">
                        {bindingSite.ligand_found ? (
                          <Badge variant="secondary" className="bg-[#00D4AA]/15 text-[#00D4AA] border border-[#00D4AA]/30">
                            {bindingSite.ligand_resname ? String(bindingSite.ligand_resname) : 'Found'}
                          </Badge>
                        ) : (
                          <span className="text-sm text-[#8B949E]">None detected</span>
                        )}
                      </div>
                    </div>
                  </div>
                  {Array.isArray(bindingSite.residues_nearby) && bindingSite.residues_nearby.length > 0 && (
                    <div className="mt-3">
                      <p className="mb-1.5 text-xs text-[#8B949E]">Nearby Residues</p>
                      <div className="flex flex-wrap gap-1">
                        {bindingSite.residues_nearby.map((res, i) => (
                          <Badge key={i} variant="outline" className="border-[#2A2F3E] text-[#8B949E] text-[10px] font-mono px-1.5 py-0">
                            {String(res)}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              )}
            </Card>
          )}

          {smiles && (
            <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
              <CardHeader>
                <CardTitle className="text-sm text-[#FAFAFA]">Compound Identity</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-[#8B949E]">SMILES</p>
                    <pre className="mt-1 overflow-x-auto rounded border border-[#2A2F3E] bg-[#0E1117] p-2 font-mono text-xs text-[#FAFAFA]">{smiles}</pre>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    {compoundCid != null && (
                      <div>
                        <p className="text-xs text-[#8B949E]">PubChem CID</p>
                        <a
                          href={`https://pubchem.ncbi.nlm.nih.gov/compound/${compoundCid}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-sm text-[#00D4AA] hover:underline"
                        >
                          {compoundCid}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                    )}
                    {iupacName && (
                      <div>
                        <p className="text-xs text-[#8B949E]">IUPAC Name</p>
                        <p className="text-sm text-[#FAFAFA]">{iupacName}</p>
                      </div>
                    )}
                    {formula && (
                      <div>
                        <p className="text-xs text-[#8B949E]">Formula</p>
                        <p className="text-sm font-mono text-[#FAFAFA]">{formula}</p>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {admet && (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                <CardHeader><CardTitle className="text-sm text-[#FAFAFA]">Lipinski Rule of Five</CardTitle></CardHeader>
                <CardContent>
                  <table className="w-full text-sm">
                    <thead><tr className="border-b border-[#2A2F3E] text-[#8B949E]">
                      <th className="pb-2 text-left font-medium">Property</th>
                      <th className="pb-2 text-left font-medium">Value</th>
                      <th className="pb-2 text-left font-medium">Limit</th>
                      <th className="pb-2 text-left font-medium">Status</th>
                    </tr></thead>
                    <tbody className="text-[#FAFAFA]">
                      {[
                        { prop: 'MW', val: admet.mw, limit: '<=500', pass: Number(admet.mw) <= 500 },
                        { prop: 'LogP', val: admet.logp, limit: '<=5', pass: Number(admet.logp) <= 5 },
                        { prop: 'HBD', val: admet.hbd, limit: '<=5', pass: Number(admet.hbd) <= 5 },
                        { prop: 'HBA', val: admet.hba, limit: '<=10', pass: Number(admet.hba) <= 10 },
                      ].map(r => (
                        <tr key={r.prop} className="border-b border-[#2A2F3E]/50">
                          <td className="py-1.5 text-[#8B949E]">{r.prop}</td>
                          <td className="py-1.5 font-mono">{r.val != null ? Number(r.val).toFixed(2) : '--'}</td>
                          <td className="py-1.5 text-[#8B949E]">{r.limit}</td>
                          <td className="py-1.5"><span className={r.pass ? 'text-[#00D4AA]' : 'text-[#FF4B4B]'}>{r.pass ? 'Pass' : 'Fail'}</span></td>
                        </tr>
                      ))}
                    </tbody>
                    {(() => {
                      const lipinski = admet.lipinski as Record<string, unknown> | undefined
                      const violations = lipinski?.violations as number | undefined
                      if (violations == null) return null
                      const passed = 4 - violations
                      return (
                        <tfoot>
                          <tr>
                            <td colSpan={4} className="pt-2 text-xs text-[#8B949E]">
                              <span className={passed >= 3 ? 'text-[#00D4AA]' : 'text-[#FFD700]'}>
                                {passed}/4 rules passed
                              </span>
                              {' '}({violations} violation{violations !== 1 ? 's' : ''})
                            </td>
                          </tr>
                        </tfoot>
                      )
                    })()}
                  </table>
                  {admet.rotatable_bonds != null && (
                    <>
                      <h4 className="mt-4 text-sm font-medium text-[#FAFAFA]">Veber Rules</h4>
                      <table className="mt-1 w-full text-sm">
                        <tbody className="text-[#FAFAFA]">
                          <tr className="border-b border-[#2A2F3E]/50">
                            <td className="py-1.5 text-[#8B949E]">RotBonds</td>
                            <td className="py-1.5 font-mono">{String(admet.rotatable_bonds)}</td>
                            <td className="py-1.5 text-[#8B949E]">{'<=10'}</td>
                            <td className="py-1.5"><span className={Number(admet.rotatable_bonds) <= 10 ? 'text-[#00D4AA]' : 'text-[#FF4B4B]'}>{Number(admet.rotatable_bonds) <= 10 ? 'Pass' : 'Fail'}</span></td>
                          </tr>
                          <tr className="border-b border-[#2A2F3E]/50">
                            <td className="py-1.5 text-[#8B949E]">TPSA</td>
                            <td className="py-1.5 font-mono">{admet.tpsa != null ? Number(admet.tpsa).toFixed(1) : '--'}</td>
                            <td className="py-1.5 text-[#8B949E]">{'<=140'}</td>
                            <td className="py-1.5"><span className={Number(admet.tpsa) <= 140 ? 'text-[#00D4AA]' : 'text-[#FF4B4B]'}>{Number(admet.tpsa) <= 140 ? 'Pass' : 'Fail'}</span></td>
                          </tr>
                        </tbody>
                        {(() => {
                          const veber = admet.veber as Record<string, unknown> | undefined
                          const violations = veber?.violations as number | undefined
                          if (violations == null) return null
                          const passed = 2 - violations
                          return (
                            <tfoot>
                              <tr>
                                <td colSpan={4} className="pt-2 text-xs text-[#8B949E]">
                                  <span className={passed >= 2 ? 'text-[#00D4AA]' : 'text-[#FFD700]'}>
                                    {passed}/2 rules passed
                                  </span>
                                  {' '}({violations} violation{violations !== 1 ? 's' : ''})
                                </td>
                              </tr>
                            </tfoot>
                          )
                        })()}
                      </table>
                    </>
                  )}
                </CardContent>
              </Card>
              <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                <CardContent className="pt-4">
                  <AdmetRadar admet={admet} compoundName={compoundName || compound} />
                </CardContent>
              </Card>
            </div>
          )}

          {(allPoses ?? allEnergies) && (allPoses?.length ?? allEnergies?.length ?? 0) > 0 && (
            <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
              <CardHeader>
                <CardTitle className="text-[#FAFAFA]">Pose Energies</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-[#2A2F3E] text-[#8B949E]">
                        <th className="pb-2 pr-4 font-medium">Pose</th>
                        <th className="pb-2 pr-4 font-medium">Energy (kcal/mol)</th>
                        {allPoses && <th className="pb-2 pr-4 font-medium">RMSD LB</th>}
                        {allPoses && <th className="pb-2 font-medium">RMSD UB</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {allPoses
                        ? allPoses.map((pose, i) => {
                            const q = bindingQuality(pose.affinity)
                            return (
                              <tr key={i} className="border-b border-[#2A2F3E]/50">
                                <td className="py-2 pr-4 font-mono text-[#FAFAFA]">{i + 1}</td>
                                <td className="py-2 pr-4" style={{ color: q.color }}>
                                  {pose.affinity.toFixed(1)}
                                </td>
                                <td className="py-2 pr-4 font-mono text-[#8B949E]">{pose.rmsd_lb.toFixed(2)}</td>
                                <td className="py-2 font-mono text-[#8B949E]">{pose.rmsd_ub.toFixed(2)}</td>
                              </tr>
                            )
                          })
                        : allEnergies?.map((energy, i) => {
                            const q = bindingQuality(energy)
                            return (
                              <tr key={i} className="border-b border-[#2A2F3E]/50">
                                <td className="py-2 pr-4 font-mono text-[#FAFAFA]">{i + 1}</td>
                                <td className="py-2" style={{ color: q.color }}>
                                  {energy.toFixed(1)}
                                </td>
                              </tr>
                            )
                          })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {allEnergies && allEnergies.length > 1 && (
            <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
              <CardContent className="pt-4">
                <EnergyBarChart
                  runs={allEnergies.map((e, i) => ({
                    name: `Pose ${i + 1}`,
                    best_energy: e,
                  }))}
                />
              </CardContent>
            </Card>
          )}

          {files.length > 0 && (
            <div>
              <h2 className="mb-3 text-base font-semibold text-[#FAFAFA]">Output Files</h2>
              <FilePanel files={files} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
