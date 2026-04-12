'use client'

import { useState, useEffect, useCallback } from 'react'
import { apiGet, apiGetText, apiPost } from '@/lib/api'
import type { DockingRun, PaginatedResponse } from '@/lib/types'
import { DynamicMol3DViewer } from '@/components/mol3d/dynamic-viewer'
import { MetricCard } from '@/components/metric-card'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ChevronDown, ChevronRight, Info } from 'lucide-react'

type ProteinStyle = 'cartoon' | 'stick' | 'sphere' | 'line'

interface RunOption {
  id: string
  label: string
  pdbId: string
  bestEnergy: number | null
  exhaustiveness: number | null
  compoundName: string
  allEnergies: number[] | null
  interactions: Record<string, unknown> | null
}

export default function ViewerPage() {
  const [runs, setRuns] = useState<RunOption[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string>('')
  const [proteinStyle, setProteinStyle] = useState<ProteinStyle>('cartoon')
  const [showSurface, setShowSurface] = useState(false)
  const [showHbonds, setShowHbonds] = useState(true)
  const [bgColor, setBgColor] = useState('#0E1117')

  const [proteinContent, setProteinContent] = useState<string | null>(null)
  const [ligandContent, setLigandContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [pdbInput, setPdbInput] = useState('')
  const [fetchingProtein, setFetchingProtein] = useState(false)
  const [proteinOnlyContent, setProteinOnlyContent] = useState<string | null>(null)

  const [posesExpanded, setPosesExpanded] = useState(false)
  const [interactionsExpanded, setInteractionsExpanded] = useState(true)
  const [analyzingInteractions, setAnalyzingInteractions] = useState(false)
  const [interactionData, setInteractionData] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    async function fetchRuns() {
      try {
        const data = await apiGet<PaginatedResponse<DockingRun>>('/api/results?limit=100')
        const options: RunOption[] = data.items.map((r) => {
          const compound = r.compounds?.name || 'Unknown'
          const protein = r.proteins?.pdb_id || 'Unknown'
          const energy = r.best_energy != null ? `${r.best_energy.toFixed(1)} kcal/mol` : 'N/A'
          return {
            id: r.id,
            label: `${compound} vs ${protein} (${energy})`,
            pdbId: r.proteins?.pdb_id || '',
            bestEnergy: r.best_energy ?? null,
            exhaustiveness: r.exhaustiveness ?? null,
            compoundName: compound,
            allEnergies: r.all_energies ?? null,
            interactions: r.interactions ?? null,
          }
        })
        setRuns(options)
      } catch {
        // runs may not be available yet
      }
    }
    fetchRuns()
  }, [])

  const selectedRun = runs.find((r) => r.id === selectedRunId) ?? null

  // Use locally fetched interaction data if available, fallback to run's stored data
  const activeInteractions = interactionData ?? selectedRun?.interactions ?? null

  async function runInteractionAnalysis() {
    if (!selectedRunId) return
    setAnalyzingInteractions(true)
    try {
      const result = await apiPost<Record<string, unknown>>(`/api/results/${selectedRunId}/interactions`, {})
      setInteractionData(result)
      // Update the run in the list too
      setRuns(prev => prev.map(r => r.id === selectedRunId ? { ...r, interactions: result } : r))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run interaction analysis')
    } finally {
      setAnalyzingInteractions(false)
    }
  }

  // Reset interaction data when run changes
  useEffect(() => {
    setInteractionData(null)
  }, [selectedRunId])

  const loadRunFiles = useCallback(async (run: RunOption) => {
    setLoading(true)
    setError(null)
    setProteinContent(null)
    setLigandContent(null)
    setProteinOnlyContent(null)
    try {
      const [protein, ligand] = await Promise.all([
        apiGetText(`/api/proteins/${run.pdbId}/file`),
        apiGetText(`/api/results/${run.id}/file`),
      ])
      setProteinContent(protein)
      setLigandContent(ligand)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load files')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectedRun) {
      loadRunFiles(selectedRun)
    }
  }, [selectedRun, loadRunFiles])

  async function handleFetchProtein() {
    if (!pdbInput.trim()) return
    setFetchingProtein(true)
    setError(null)
    setProteinOnlyContent(null)
    setProteinContent(null)
    setLigandContent(null)
    setSelectedRunId('')
    try {
      await apiPost('/api/proteins/fetch', { pdb_id: pdbInput.trim().toUpperCase() })
      const content = await apiGetText(`/api/proteins/${pdbInput.trim().toUpperCase()}/file`)
      setProteinOnlyContent(content)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch protein')
    } finally {
      setFetchingProtein(false)
    }
  }

  const bgHex = bgColor.startsWith('#')
    ? '0x' + bgColor.slice(1)
    : bgColor

  const interactionCounts = activeInteractions
    ? {
        hbonds: Array.isArray((activeInteractions as Record<string, unknown>).hydrogen_bonds)
          ? (activeInteractions.hydrogen_bonds as unknown[]).length
          : 0,
        hydrophobic: Array.isArray((activeInteractions as Record<string, unknown>).hydrophobic_contacts)
          ? (activeInteractions.hydrophobic_contacts as unknown[]).length
          : 0,
        saltBridges: Array.isArray((activeInteractions as Record<string, unknown>).salt_bridges)
          ? (activeInteractions.salt_bridges as unknown[]).length
          : 0,
        piStacking: Array.isArray((activeInteractions as Record<string, unknown>).pi_stacking)
          ? (activeInteractions.pi_stacking as unknown[]).length
          : 0,
      }
    : null

  return (
    <div className="min-h-screen bg-[#0E1117] p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <h1 className="text-2xl font-bold text-[#00D4AA]">3D Viewer</h1>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
          {/* Controls */}
          <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
            <CardHeader>
              <CardTitle className="text-[#FAFAFA]">Controls</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="text-[#8B949E]">Docking Run</Label>
                <Select value={selectedRunId} onValueChange={(v) => setSelectedRunId(v ?? '')}>
                  <SelectTrigger className="w-full border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]">
                    <SelectValue placeholder="Select a run..." />
                  </SelectTrigger>
                  <SelectContent className="border-[#2A2F3E] bg-[#1A1F2E]">
                    {runs.map((r) => (
                      <SelectItem key={r.id} value={r.id} className="text-[#FAFAFA]">
                        {r.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label className="text-[#8B949E]">Protein Style</Label>
                <Select value={proteinStyle} onValueChange={(v) => setProteinStyle(v as ProteinStyle)}>
                  <SelectTrigger className="w-full border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-[#2A2F3E] bg-[#1A1F2E]">
                    <SelectItem value="cartoon" className="text-[#FAFAFA]">Cartoon</SelectItem>
                    <SelectItem value="stick" className="text-[#FAFAFA]">Stick</SelectItem>
                    <SelectItem value="sphere" className="text-[#FAFAFA]">Sphere</SelectItem>
                    <SelectItem value="line" className="text-[#FAFAFA]">Line</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2">
                <Checkbox
                  checked={showSurface}
                  onCheckedChange={(v) => setShowSurface(v === true)}
                />
                <Label className="text-[#FAFAFA]">Show Surface</Label>
              </div>

              <div className="flex items-center gap-2">
                <Checkbox
                  checked={showHbonds}
                  onCheckedChange={(v) => setShowHbonds(v === true)}
                />
                <Label className="text-[#FAFAFA]">Show H-bonds</Label>
              </div>

              <div className="space-y-2">
                <Label className="text-[#8B949E]">Background Color</Label>
                <div className="flex gap-2">
                  <input
                    type="color"
                    value={bgColor}
                    onChange={(e) => setBgColor(e.target.value)}
                    className="h-8 w-10 cursor-pointer rounded border border-[#2A2F3E] bg-transparent"
                  />
                  <Input
                    value={bgColor}
                    onChange={(e) => setBgColor(e.target.value)}
                    className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Viewer Area */}
          <div className="space-y-4">
            {error && (
              <div className="rounded-lg border border-red-500/50 bg-red-950/30 p-4">
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            {loading && (
              <div className="flex h-[600px] items-center justify-center rounded-lg border border-[#2A2F3E] bg-[#1A1F2E]">
                <div className="flex items-center gap-3">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-[#00D4AA] border-t-transparent" />
                  <span className="text-[#8B949E]">Loading structure...</span>
                </div>
              </div>
            )}

            {!loading && proteinContent && (
              <DynamicMol3DViewer
                proteinContent={proteinContent}
                ligandContent={ligandContent ?? undefined}
                style={proteinStyle}
                showSurface={showSurface}
                showHbonds={showHbonds}
                interactions={activeInteractions as { hydrogen_bonds?: Array<{ donor_coords?: number[]; acceptor_coords?: number[] }> } | undefined}
                bgColor={bgHex}
                width={800}
                height={600}
              />
            )}

            {!loading && proteinOnlyContent && !proteinContent && (
              <DynamicMol3DViewer
                proteinContent={proteinOnlyContent}
                style={proteinStyle}
                showSurface={showSurface}
                showHbonds={false}
                bgColor={bgHex}
                width={800}
                height={600}
              />
            )}

            {!loading && !proteinContent && !proteinOnlyContent && !error && (
              <div className="space-y-4">
                {runs.length === 0 && (
                  <div className="flex items-start gap-3 rounded-lg border border-[#2A2F3E] bg-[#1A1F2E] p-4">
                    <Info className="mt-0.5 h-5 w-5 shrink-0 text-[#00D4AA]" />
                    <p className="text-sm text-[#8B949E]">
                      No docking runs found. Enter a PDB ID below to view just a protein.
                    </p>
                  </div>
                )}
                <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                  <CardContent className="pt-4">
                    <div className="flex gap-2">
                      <Input
                        placeholder="Enter PDB ID (e.g. 3S7S)"
                        value={pdbInput}
                        onChange={(e) => setPdbInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleFetchProtein()}
                        className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                      />
                      <Button
                        onClick={handleFetchProtein}
                        disabled={fetchingProtein || !pdbInput.trim()}
                        className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
                      >
                        {fetchingProtein ? 'Fetching...' : 'View'}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}

            {/* Metrics */}
            {selectedRun && !loading && (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <MetricCard
                    label="Best Energy"
                    value={selectedRun.bestEnergy != null ? `${selectedRun.bestEnergy.toFixed(1)} kcal/mol` : 'N/A'}
                    deltaColor={
                      selectedRun.bestEnergy != null && selectedRun.bestEnergy < -7
                        ? '#00D4AA'
                        : '#8B949E'
                    }
                  />
                  <MetricCard
                    label="Exhaustiveness"
                    value={selectedRun.exhaustiveness ?? 'N/A'}
                  />
                  <MetricCard
                    label="Compound"
                    value={selectedRun.compoundName}
                  />
                </div>

                {/* All Pose Energies */}
                {selectedRun.allEnergies && selectedRun.allEnergies.length > 0 && (
                  <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                    <button
                      onClick={() => setPosesExpanded(!posesExpanded)}
                      className="flex w-full items-center justify-between px-4 py-3 text-left"
                    >
                      <span className="text-sm font-medium text-[#FAFAFA]">
                        All Pose Energies ({selectedRun.allEnergies.length})
                      </span>
                      {posesExpanded
                        ? <ChevronDown className="h-4 w-4 text-[#8B949E]" />
                        : <ChevronRight className="h-4 w-4 text-[#8B949E]" />}
                    </button>
                    {posesExpanded && (
                      <CardContent className="border-t border-[#2A2F3E] pt-3">
                        <div className="space-y-1">
                          {selectedRun.allEnergies.map((e, i) => (
                            <div key={i} className="flex justify-between text-sm">
                              <span className="text-[#8B949E]">Pose {i + 1}</span>
                              <span className={e < -7 ? 'text-[#00D4AA]' : 'text-[#FAFAFA]'}>
                                {e.toFixed(1)} kcal/mol
                              </span>
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    )}
                  </Card>
                )}

                {/* Interaction Analysis */}
                <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                  <button
                    onClick={() => setInteractionsExpanded(!interactionsExpanded)}
                    className="flex w-full items-center justify-between px-4 py-3 text-left"
                  >
                    <span className="text-sm font-medium text-[#FAFAFA]">
                      Protein-Ligand Interactions
                      {interactionCounts ? ` (${interactionCounts.hbonds + interactionCounts.hydrophobic + interactionCounts.saltBridges + interactionCounts.piStacking} total)` : ''}
                    </span>
                    {interactionsExpanded
                      ? <ChevronDown className="h-4 w-4 text-[#8B949E]" />
                      : <ChevronRight className="h-4 w-4 text-[#8B949E]" />}
                  </button>
                  {interactionsExpanded && (
                    <CardContent className="border-t border-[#2A2F3E] pt-3 space-y-4">
                      {!interactionCounts && (
                        <div className="space-y-2">
                          <p className="text-sm text-[#8B949E]">
                            Run PLIP analysis to identify hydrogen bonds, hydrophobic contacts, salt bridges, and pi-stacking interactions.
                          </p>
                          <Button
                            onClick={runInteractionAnalysis}
                            disabled={analyzingInteractions}
                            className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
                          >
                            {analyzingInteractions ? 'Analyzing...' : 'Run Interaction Analysis'}
                          </Button>
                        </div>
                      )}

                      {interactionCounts && (
                        <>
                          <div className="grid grid-cols-4 gap-3">
                            <div className="rounded-lg bg-[#0E1117] p-3 text-center">
                              <div className="text-lg font-bold text-yellow-400">{interactionCounts.hbonds}</div>
                              <div className="text-xs text-[#8B949E]">H-bonds</div>
                            </div>
                            <div className="rounded-lg bg-[#0E1117] p-3 text-center">
                              <div className="text-lg font-bold text-green-400">{interactionCounts.hydrophobic}</div>
                              <div className="text-xs text-[#8B949E]">Hydrophobic</div>
                            </div>
                            <div className="rounded-lg bg-[#0E1117] p-3 text-center">
                              <div className="text-lg font-bold text-blue-400">{interactionCounts.saltBridges}</div>
                              <div className="text-xs text-[#8B949E]">Salt Bridges</div>
                            </div>
                            <div className="rounded-lg bg-[#0E1117] p-3 text-center">
                              <div className="text-lg font-bold text-purple-400">{interactionCounts.piStacking}</div>
                              <div className="text-xs text-[#8B949E]">Pi-stacking</div>
                            </div>
                          </div>

                          {/* Detailed H-bond list */}
                          {Array.isArray((activeInteractions as Record<string, unknown>)?.hydrogen_bonds) &&
                            ((activeInteractions as Record<string, unknown>).hydrogen_bonds as Array<Record<string, unknown>>).length > 0 && (
                            <div className="space-y-1">
                              <h4 className="text-sm font-medium text-yellow-400">Hydrogen Bonds</h4>
                              {((activeInteractions as Record<string, unknown>).hydrogen_bonds as Array<Record<string, unknown>>).map((hb, i) => (
                                <div key={i} className="flex items-center gap-2 text-xs text-[#8B949E]">
                                  <span className="inline-block h-2 w-2 rounded-full bg-yellow-400" />
                                  <span>{String(hb.donor_residue || hb.donor || '?')}</span>
                                  <span className="text-[#4A4F5E]">--</span>
                                  <span>{String(hb.acceptor_residue || hb.acceptor || '?')}</span>
                                  {hb.distance != null && <span className="text-[#4A4F5E]">({Number(hb.distance).toFixed(1)} A)</span>}
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Detailed hydrophobic list */}
                          {Array.isArray((activeInteractions as Record<string, unknown>)?.hydrophobic_contacts) &&
                            ((activeInteractions as Record<string, unknown>).hydrophobic_contacts as Array<Record<string, unknown>>).length > 0 && (
                            <div className="space-y-1">
                              <h4 className="text-sm font-medium text-green-400">Hydrophobic Contacts</h4>
                              {((activeInteractions as Record<string, unknown>).hydrophobic_contacts as Array<Record<string, unknown>>).map((c, i) => (
                                <div key={i} className="flex items-center gap-2 text-xs text-[#8B949E]">
                                  <span className="inline-block h-2 w-2 rounded-full bg-green-400" />
                                  <span>{String(c.residue || c.name || `Contact ${i + 1}`)}</span>
                                  {c.distance != null && <span className="text-[#4A4F5E]">({Number(c.distance).toFixed(1)} A)</span>}
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Re-run button */}
                          <Button
                            onClick={runInteractionAnalysis}
                            disabled={analyzingInteractions}
                            variant="outline"
                            size="sm"
                            className="border-[#2A2F3E] text-[#8B949E] hover:bg-[#2A2F3E]"
                          >
                            {analyzingInteractions ? 'Analyzing...' : 'Re-run Analysis'}
                          </Button>
                        </>
                      )}
                    </CardContent>
                  )}
                </Card>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
