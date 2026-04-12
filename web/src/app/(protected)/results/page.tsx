'use client'

import { useState, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Download, FileText, ArrowUpDown, ChevronDown, ChevronRight } from 'lucide-react'
import { apiGet, apiPost } from '@/lib/api'
import type { Protein, DockingRun } from '@/lib/types'
import { MetricCard } from '@/components/metric-card'
import { EnergyBarChart } from '@/components/charts/energy-bar-chart'
import { EnergyHistogram } from '@/components/charts/energy-histogram'
import { FilePanel } from '@/components/file-panel'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select'

type SortKey = 'pdb_id' | 'compound' | 'energy' | 'exhaustiveness' | 'date'
type SortDir = 'asc' | 'desc'

interface Filters {
  proteinId: string
  energyMin: number
  energyMax: number
  limit: number
}

function buildQueryString(f: Filters): string {
  const params = new URLSearchParams()
  if (f.proteinId && f.proteinId !== 'all') params.set('protein_id', f.proteinId)
  params.set('energy_min', String(f.energyMin))
  params.set('energy_max', String(f.energyMax))
  params.set('limit', String(f.limit))
  return params.toString()
}

function formatDate(d: string | null | undefined): string {
  if (!d) return 'N/A'
  try {
    return new Date(d).toLocaleDateString()
  } catch {
    return d
  }
}

function formatEnergy(e: number | null | undefined): string {
  if (e == null) return 'N/A'
  return e.toFixed(2)
}

function getRunLabel(run: DockingRun): string {
  const protein = run.proteins?.pdb_id ?? run.protein_id
  const compound = run.compounds?.name ?? run.compound_id
  return `${protein} / ${compound}`
}

export default function ResultsPage() {
  const [filters, setFilters] = useState<Filters>({
    proteinId: 'all',
    energyMin: -15,
    energyMax: 0,
    limit: 20,
  })
  const [appliedFilters, setAppliedFilters] = useState<Filters>(filters)
  const [filtersOpen, setFiltersOpen] = useState(true)
  const [sortKey, setSortKey] = useState<SortKey>('energy')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [exporting, setExporting] = useState(false)

  const { data: proteins } = useQuery({
    queryKey: ['proteins'],
    queryFn: async () => {
      const res = await apiGet<{ items: Protein[] }>('/api/proteins')
      return res.items ?? []
    },
  })

  const queryString = buildQueryString(appliedFilters)
  const { data: runs, isLoading: runsLoading, error: runsError } = useQuery({
    queryKey: ['results', queryString],
    queryFn: async () => {
      const res = await apiGet<{ items: DockingRun[] }>(`/api/results?${queryString}`)
      return res.items ?? []
    },
  })

  const { data: runDetail, isLoading: detailLoading } = useQuery({
    queryKey: ['result-detail', selectedRunId],
    queryFn: () => apiGet<DockingRun>(`/api/results/${selectedRunId}`),
    enabled: !!selectedRunId,
  })

  const handleApplyFilters = useCallback(() => {
    setAppliedFilters({ ...filters })
  }, [filters])

  const toggleSort = useCallback((key: SortKey) => {
    setSortKey((prev) => {
      if (prev === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
        return key
      }
      setSortDir('asc')
      return key
    })
  }, [])

  const sortedRuns = useMemo(() => {
    if (!runs) return []
    const sorted = [...runs].sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case 'pdb_id':
          cmp = (a.proteins?.pdb_id ?? '').localeCompare(b.proteins?.pdb_id ?? '')
          break
        case 'compound':
          cmp = (a.compounds?.name ?? '').localeCompare(b.compounds?.name ?? '')
          break
        case 'energy':
          cmp = (a.best_energy ?? 0) - (b.best_energy ?? 0)
          break
        case 'exhaustiveness':
          cmp = (a.exhaustiveness ?? 0) - (b.exhaustiveness ?? 0)
          break
        case 'date':
          cmp = (a.created_at ?? '').localeCompare(b.created_at ?? '')
          break
      }
      return sortDir === 'desc' ? -cmp : cmp
    })
    return sorted
  }, [runs, sortKey, sortDir])

  const barChartData = useMemo(() => {
    return sortedRuns
      .filter((r) => r.best_energy != null)
      .map((r) => ({
        compound_name: getRunLabel(r),
        best_energy: r.best_energy!,
      }))
  }, [sortedRuns])

  const toggleCompare = useCallback((id: string) => {
    setCompareIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= 8) return prev
      return [...prev, id]
    })
  }, [])

  const compareRuns = useMemo(() => {
    return sortedRuns.filter((r) => compareIds.includes(r.id))
  }, [sortedRuns, compareIds])

  const handleExportCSV = useCallback(() => {
    if (!sortedRuns.length) return
    const header = 'Protein PDB ID,Compound,Energy (kcal/mol),Exhaustiveness,Date\n'
    const rows = sortedRuns
      .map((r) =>
        [
          r.proteins?.pdb_id ?? r.protein_id,
          r.compounds?.name ?? r.compound_id,
          formatEnergy(r.best_energy),
          r.exhaustiveness ?? '',
          formatDate(r.created_at),
        ].join(',')
      )
      .join('\n')
    const blob = new Blob([header + rows], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'docking_results.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [sortedRuns])

  const handleExportDocx = useCallback(async () => {
    if (!sortedRuns.length) return
    setExporting(true)
    try {
      await apiPost('/api/export', {
        format: 'docx',
        run_ids: sortedRuns.map((r) => r.id),
      })
    } catch {
      // export failed
    } finally {
      setExporting(false)
    }
  }, [sortedRuns])

  const SortHeader = ({ label, field }: { label: string; field: SortKey }) => (
    <th className="py-2 pr-3 text-left text-[#8B949E] font-medium">
      <button onClick={() => toggleSort(field)} className="inline-flex items-center gap-1 hover:text-[#FAFAFA]">
        {label}
        <ArrowUpDown className="h-3 w-3" />
        {sortKey === field && <span className="text-[#00D4AA] text-xs">{sortDir === 'asc' ? 'asc' : 'desc'}</span>}
      </button>
    </th>
  )

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-[#FAFAFA]">Docking Results</h1>
        <p className="mt-1 text-sm text-[#8B949E]">Browse, filter, and analyze docking runs</p>
      </div>

      {/* Filters */}
      <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
        <button
          onClick={() => setFiltersOpen((p) => !p)}
          className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium text-[#FAFAFA] hover:bg-[#2A2F3E]/30"
        >
          {filtersOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Filters
        </button>
        {filtersOpen && (
          <CardContent className="space-y-4 border-t border-[#2A2F3E]">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-2">
                <Label className="text-[#FAFAFA]">Protein</Label>
                <Select
                  value={filters.proteinId}
                  onValueChange={(val) => setFilters((f) => ({ ...f, proteinId: val as string }))}
                >
                  <SelectTrigger className="w-full border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]">
                    <SelectValue placeholder="All proteins" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    {(proteins ?? []).map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.pdb_id}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label className="text-[#FAFAFA]">Energy Min (kcal/mol)</Label>
                <Input
                  type="number"
                  value={filters.energyMin}
                  onChange={(e) => setFilters((f) => ({ ...f, energyMin: Number(e.target.value) }))}
                  className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-[#FAFAFA]">Energy Max (kcal/mol)</Label>
                <Input
                  type="number"
                  value={filters.energyMax}
                  onChange={(e) => setFilters((f) => ({ ...f, energyMax: Number(e.target.value) }))}
                  className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-[#FAFAFA]">Limit: {filters.limit}</Label>
                <Slider
                  min={10}
                  max={100}
                  value={[filters.limit]}
                  onValueChange={(val) => setFilters((f) => ({ ...f, limit: Array.isArray(val) ? val[0] : val }))}
                />
              </div>
            </div>

            <Button
              onClick={handleApplyFilters}
              className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
            >
              Apply Filters
            </Button>
          </CardContent>
        )}
      </Card>

      {/* Loading / error */}
      {runsLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-[#00D4AA]" />
        </div>
      )}

      {runsError && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {runsError instanceof Error ? runsError.message : 'Failed to load results'}
        </div>
      )}

      {runs && runs.length === 0 && !runsLoading && (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardContent className="py-12 text-center text-[#8B949E]">
            No docking results match your filters.
          </CardContent>
        </Card>
      )}

      {sortedRuns.length > 0 && (
        <>
          {/* Results Table */}
          <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
            <CardHeader>
              <CardTitle className="text-[#FAFAFA]">Results ({sortedRuns.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#2A2F3E]">
                      <th className="py-2 pr-3 w-8" />
                      <SortHeader label="Protein PDB ID" field="pdb_id" />
                      <SortHeader label="Compound" field="compound" />
                      <SortHeader label="Energy (kcal/mol)" field="energy" />
                      <SortHeader label="Exhaustiveness" field="exhaustiveness" />
                      <SortHeader label="Date" field="date" />
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRuns.map((run) => (
                      <tr key={run.id} className="border-b border-[#2A2F3E]/50 hover:bg-[#2A2F3E]/20">
                        <td className="py-2 pr-3">
                          <Checkbox
                            checked={compareIds.includes(run.id)}
                            onCheckedChange={() => toggleCompare(run.id)}
                          />
                        </td>
                        <td className="py-2 pr-3 text-[#FAFAFA]">{run.proteins?.pdb_id ?? run.protein_id}</td>
                        <td className="py-2 pr-3 text-[#FAFAFA]">{run.compounds?.name ?? run.compound_id}</td>
                        <td className="py-2 pr-3 font-mono">
                          <span className={
                            run.best_energy != null && run.best_energy < -8
                              ? 'text-[#00D4AA]'
                              : run.best_energy != null && run.best_energy <= -7
                                ? 'text-[#FFD700]'
                                : 'text-[#FF4B4B]'
                          }>
                            {formatEnergy(run.best_energy)}
                          </span>
                        </td>
                        <td className="py-2 pr-3 text-[#FAFAFA]">{run.exhaustiveness ?? 'N/A'}</td>
                        <td className="py-2 text-[#8B949E]">{formatDate(run.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Tabs */}
          <Tabs defaultValue="bar">
            <TabsList>
              <TabsTrigger value="bar">Bar Chart</TabsTrigger>
              <TabsTrigger value="distribution">Distribution</TabsTrigger>
              <TabsTrigger value="details">Run Details</TabsTrigger>
              <TabsTrigger value="compare">Compare</TabsTrigger>
            </TabsList>

            <TabsContent value="bar">
              <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                <CardContent className="pt-4">
                  <EnergyBarChart runs={barChartData} />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="distribution">
              <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                <CardContent className="pt-4">
                  <EnergyHistogram runs={sortedRuns.map((r) => ({ best_energy: r.best_energy ?? undefined }))} />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="details">
              <div className="space-y-4">
                <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                  <CardContent className="pt-4">
                    <Label className="text-[#FAFAFA]">Select a Run</Label>
                    <Select
                      value={selectedRunId ?? undefined}
                      onValueChange={(val) => setSelectedRunId(val as string)}
                    >
                      <SelectTrigger className="mt-2 w-full border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]">
                        <SelectValue placeholder="Choose a docking run" />
                      </SelectTrigger>
                      <SelectContent>
                        {sortedRuns.map((r) => (
                          <SelectItem key={r.id} value={r.id}>
                            {getRunLabel(r)} ({formatEnergy(r.best_energy)} kcal/mol)
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </CardContent>
                </Card>

                {detailLoading && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-[#00D4AA]" />
                  </div>
                )}

                {runDetail && (
                  <>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      <MetricCard
                        label="Protein"
                        value={runDetail.proteins?.pdb_id ?? runDetail.protein_id}
                      />
                      <MetricCard
                        label="Compound"
                        value={runDetail.compounds?.name ?? runDetail.compound_id}
                      />
                      <MetricCard
                        label="Best Energy"
                        value={`${formatEnergy(runDetail.best_energy)} kcal/mol`}
                        delta={
                          runDetail.best_energy != null && runDetail.best_energy < -7
                            ? 'Promising'
                            : 'Weak'
                        }
                        deltaColor={
                          runDetail.best_energy != null && runDetail.best_energy < -7
                            ? '#00D4AA'
                            : '#FF4B4B'
                        }
                      />
                      <MetricCard
                        label="Exhaustiveness"
                        value={runDetail.exhaustiveness ?? 'N/A'}
                      />
                    </div>

                    <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                      <CardHeader>
                        <CardTitle className="text-[#FAFAFA]">Run Details</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
                          <div>
                            <span className="text-[#8B949E]">Date: </span>
                            <span className="text-[#FAFAFA]">{formatDate(runDetail.created_at)}</span>
                          </div>
                          {(runDetail.center_x != null || runDetail.center_y != null || runDetail.center_z != null) && (
                            <div>
                              <span className="text-[#8B949E]">Search Box Center: </span>
                              <span className="text-[#FAFAFA] font-mono">
                                ({runDetail.center_x?.toFixed(1)}, {runDetail.center_y?.toFixed(1)}, {runDetail.center_z?.toFixed(1)})
                              </span>
                            </div>
                          )}
                          {(runDetail.size_x != null || runDetail.size_y != null || runDetail.size_z != null) && (
                            <div>
                              <span className="text-[#8B949E]">Search Box Size: </span>
                              <span className="text-[#FAFAFA] font-mono">
                                ({runDetail.size_x?.toFixed(1)}, {runDetail.size_y?.toFixed(1)}, {runDetail.size_z?.toFixed(1)})
                              </span>
                            </div>
                          )}
                        </div>
                      </CardContent>
                    </Card>

                    {runDetail.all_energies && runDetail.all_energies.length > 0 && (
                      <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                        <CardHeader>
                          <CardTitle className="text-[#FAFAFA]">Pose Energies</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b border-[#2A2F3E]">
                                  <th className="py-2 pr-3 text-left text-[#8B949E] font-medium">Pose</th>
                                  <th className="py-2 text-left text-[#8B949E] font-medium">Energy (kcal/mol)</th>
                                </tr>
                              </thead>
                              <tbody>
                                {runDetail.all_energies.map((e, i) => (
                                  <tr key={i} className="border-b border-[#2A2F3E]/50">
                                    <td className="py-2 pr-3 text-[#FAFAFA]">{i + 1}</td>
                                    <td className="py-2 font-mono">
                                      <span className={e < -8 ? 'text-[#00D4AA]' : e <= -7 ? 'text-[#FFD700]' : 'text-[#FF4B4B]'}>
                                        {e.toFixed(2)}
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {runDetail.interactions && Object.keys(runDetail.interactions).length > 0 && (
                      <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                        <CardHeader>
                          <CardTitle className="text-[#FAFAFA]">Interactions</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-2 text-sm">
                            {Object.entries(runDetail.interactions).map(([key, val]) => (
                              <div key={key} className="flex gap-2">
                                <Badge variant="outline" className="text-[#8B949E]">{key}</Badge>
                                <span className="text-[#FAFAFA]">
                                  {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                                </span>
                              </div>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {runDetail.output_path && (
                      <FilePanel
                        files={[
                          {
                            name: runDetail.output_path.split('/').pop() ?? 'output.pdbqt',
                            type: 'docked',
                            downloadUrl: `/api/files?path=${encodeURIComponent(runDetail.output_path)}`,
                            path: runDetail.output_path,
                          },
                        ]}
                      />
                    )}
                  </>
                )}
              </div>
            </TabsContent>

            <TabsContent value="compare">
              <div className="space-y-4">
                {compareIds.length < 2 && (
                  <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                    <CardContent className="py-8 text-center text-[#8B949E]">
                      Select 2-8 runs using the checkboxes in the table above to compare.
                    </CardContent>
                  </Card>
                )}

                {compareRuns.length >= 2 && (
                  <>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      {compareRuns.map((r) => (
                        <MetricCard
                          key={r.id}
                          label={getRunLabel(r)}
                          value={`${formatEnergy(r.best_energy)} kcal/mol`}
                          delta={r.exhaustiveness ? `Exhaust: ${r.exhaustiveness}` : undefined}
                        />
                      ))}
                    </div>

                    <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                      <CardContent className="pt-4">
                        <EnergyBarChart
                          runs={compareRuns.map((r) => ({
                            compound_name: getRunLabel(r),
                            best_energy: r.best_energy ?? 0,
                          }))}
                        />
                      </CardContent>
                    </Card>
                  </>
                )}
              </div>
            </TabsContent>
          </Tabs>

          {/* Export */}
          <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
            <CardHeader>
              <CardTitle className="text-[#FAFAFA]">Export</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-3">
                <Button variant="outline" onClick={handleExportCSV} className="border-[#2A2F3E] text-[#FAFAFA]">
                  <Download className="h-4 w-4" />
                  Download CSV
                </Button>
                <Button
                  variant="outline"
                  onClick={handleExportDocx}
                  disabled={exporting}
                  className="border-[#2A2F3E] text-[#FAFAFA]"
                >
                  {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                  Export DOCX
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
