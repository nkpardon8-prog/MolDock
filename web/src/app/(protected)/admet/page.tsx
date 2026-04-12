'use client'

import { useState, useCallback, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Download, ChevronDown, ChevronRight } from 'lucide-react'
import { apiGet, apiPost } from '@/lib/api'
import type { AdmetResult, Compound } from '@/lib/types'
import { MetricCard } from '@/components/metric-card'
import { AdmetRadar } from '@/components/charts/admet-radar'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'

const PROPERTY_ROWS: Array<{
  key: keyof AdmetResult
  label: string
  threshold: string
  check: (v: number) => boolean
}> = [
  { key: 'mw', label: 'Molecular Weight', threshold: '<= 500', check: (v) => v <= 500 },
  { key: 'logp', label: 'LogP', threshold: '<= 5', check: (v) => v <= 5 },
  { key: 'hbd', label: 'H-Bond Donors', threshold: '<= 5', check: (v) => v <= 5 },
  { key: 'hba', label: 'H-Bond Acceptors', threshold: '<= 10', check: (v) => v <= 10 },
  { key: 'rotatable_bonds', label: 'Rotatable Bonds', threshold: '<= 10', check: (v) => v <= 10 },
  { key: 'tpsa', label: 'TPSA', threshold: '<= 140', check: (v) => v <= 140 },
  { key: 'num_rings', label: 'Rings', threshold: '-', check: () => true },
  { key: 'num_aromatic_rings', label: 'Aromatic Rings', threshold: '-', check: () => true },
  { key: 'fraction_csp3', label: 'Fraction Csp3', threshold: '-', check: () => true },
  { key: 'molar_refractivity', label: 'Molar Refractivity', threshold: '40-130', check: (v) => v >= 40 && v <= 130 },
  { key: 'num_heavy_atoms', label: 'Heavy Atoms', threshold: '-', check: () => true },
]

interface BatchEntry {
  name: string
  smiles: string
  result: AdmetResult | null
  error: string | null
  status: 'pending' | 'running' | 'done' | 'error'
}

function formatNum(v: number | null | undefined): string {
  if (v == null) return 'N/A'
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
}

function SingleCompoundTab() {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AdmetResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleCheck = useCallback(async () => {
    if (!input.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await apiPost<AdmetResult>('/api/admet', { smiles: input.trim() })
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ADMET check failed')
    } finally {
      setLoading(false)
    }
  }, [input])

  return (
    <div className="space-y-6">
      <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
        <CardContent className="pt-4">
          <div className="flex gap-3 items-end">
            <div className="flex-1 space-y-2">
              <Label className="text-[#FAFAFA]">SMILES or Compound Name</Label>
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O or aspirin"
                className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                onKeyDown={(e) => { if (e.key === 'Enter') handleCheck() }}
              />
            </div>
            <Button
              onClick={handleCheck}
              disabled={loading || !input.trim()}
              className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              Check
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && !result && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-[#00D4AA]" />
        </div>
      )}

      {result && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Drug-Likeness Score"
              value={formatNum(result.drug_likeness_score)}
              delta={result.drug_likeness_score != null && result.drug_likeness_score >= 0.5 ? 'Promising' : 'Low'}
              deltaColor={result.drug_likeness_score != null && result.drug_likeness_score >= 0.5 ? '#00D4AA' : '#FF4B4B'}
            />
            <MetricCard
              label="Assessment"
              value={result.assessment ?? 'N/A'}
            />
            <MetricCard
              label="SMILES"
              value={result.smiles.length > 20 ? result.smiles.slice(0, 20) + '...' : result.smiles}
            />
            <MetricCard
              label="SA Score"
              value={formatNum(result.sa_score)}
              delta={result.synthetic_assessment ?? undefined}
            />
          </div>

          <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
            <CardHeader>
              <CardTitle className="text-[#FAFAFA]">Molecular Properties</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#2A2F3E]">
                      <th className="py-2 pr-4 text-left text-[#8B949E] font-medium">Property</th>
                      <th className="py-2 pr-4 text-left text-[#8B949E] font-medium">Value</th>
                      <th className="py-2 pr-4 text-left text-[#8B949E] font-medium">Threshold</th>
                      <th className="py-2 text-left text-[#8B949E] font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {PROPERTY_ROWS.map((row) => {
                      const val = result[row.key] as number | null | undefined
                      const pass = val != null && row.threshold !== '-' ? row.check(val) : null
                      return (
                        <tr key={row.key} className="border-b border-[#2A2F3E]/50">
                          <td className="py-2 pr-4 text-[#FAFAFA]">{row.label}</td>
                          <td className="py-2 pr-4 text-[#FAFAFA] font-mono">{formatNum(val)}</td>
                          <td className="py-2 pr-4 text-[#8B949E]">{row.threshold}</td>
                          <td className="py-2">
                            {pass === true && <Badge variant="default" className="bg-[#00D4AA]/20 text-[#00D4AA]">Pass</Badge>}
                            {pass === false && <Badge variant="destructive">Fail</Badge>}
                            {pass === null && <span className="text-[#8B949E]">-</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
            <CardContent className="pt-4">
              <AdmetRadar admet={result as unknown as Record<string, unknown>} compoundName={input} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function BatchModeTab() {
  const [text, setText] = useState('')
  const [entries, setEntries] = useState<BatchEntry[]>([])
  const [running, setRunning] = useState(false)
  const [completed, setCompleted] = useState(0)
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const abortRef = useRef(false)

  const handleRunBatch = useCallback(async () => {
    const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
    if (lines.length === 0) return

    const parsed: BatchEntry[] = lines.map((line) => {
      const parts = line.split(',').map((s) => s.trim())
      if (parts.length >= 2) {
        return { name: parts[1], smiles: parts[0], result: null, error: null, status: 'pending' as const }
      }
      return { name: parts[0], smiles: parts[0], result: null, error: null, status: 'pending' as const }
    })

    setEntries(parsed)
    setRunning(true)
    setCompleted(0)
    abortRef.current = false

    const concurrency = 5
    let done = 0
    const queue = [...parsed.keys()]

    async function runNext() {
      while (queue.length > 0 && !abortRef.current) {
        const idx = queue.shift()!
        setEntries((prev) => {
          const next = [...prev]
          next[idx] = { ...next[idx], status: 'running' }
          return next
        })
        try {
          const result = await apiPost<AdmetResult>('/api/admet', { smiles: parsed[idx].smiles })
          setEntries((prev) => {
            const next = [...prev]
            next[idx] = { ...next[idx], result, status: 'done' }
            return next
          })
        } catch (err) {
          setEntries((prev) => {
            const next = [...prev]
            next[idx] = { ...next[idx], error: err instanceof Error ? err.message : 'Failed', status: 'error' }
            return next
          })
        }
        done++
        setCompleted(done)
      }
    }

    const workers = Array.from({ length: Math.min(concurrency, parsed.length) }, () => runNext())
    await Promise.allSettled(workers)
    setRunning(false)
  }, [text])

  const handleDownloadCSV = useCallback(() => {
    const header = 'Name,SMILES,MW,LogP,HBD,HBA,Score,Assessment,SA Score\n'
    const rows = entries
      .filter((e) => e.result)
      .map((e) => {
        const r = e.result!
        return [
          e.name,
          r.smiles,
          formatNum(r.mw),
          formatNum(r.logp),
          formatNum(r.hbd),
          formatNum(r.hba),
          formatNum(r.drug_likeness_score),
          r.assessment ?? '',
          formatNum(r.sa_score),
        ].join(',')
      })
      .join('\n')
    const blob = new Blob([header + rows], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'admet_batch_results.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [entries])

  const finishedEntries = entries.filter((e) => e.result)

  return (
    <div className="space-y-6">
      <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
        <CardContent className="pt-4 space-y-3">
          <Label className="text-[#FAFAFA]">Compounds (one per line, optionally: SMILES, Name)</Label>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"CC(=O)Oc1ccccc1C(=O)O, Aspirin\nCC(C)Cc1ccc(cc1)C(C)C(=O)O, Ibuprofen"}
            rows={6}
            className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA] font-mono text-xs"
          />
          <div className="flex items-center gap-4">
            <Button
              onClick={handleRunBatch}
              disabled={running || !text.trim()}
              className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
            >
              {running && <Loader2 className="h-4 w-4 animate-spin" />}
              Run Batch
            </Button>
            {running && (
              <span className="text-sm text-[#8B949E]">
                {completed} / {entries.length} completed
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {entries.length > 0 && (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-[#FAFAFA]">Results</CardTitle>
            {finishedEntries.length > 0 && (
              <Button variant="outline" size="sm" onClick={handleDownloadCSV} className="border-[#2A2F3E] text-[#FAFAFA]">
                <Download className="h-3.5 w-3.5" />
                CSV
              </Button>
            )}
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#2A2F3E]">
                    <th className="py-2 pr-3 text-left text-[#8B949E] font-medium">Name</th>
                    <th className="py-2 pr-3 text-left text-[#8B949E] font-medium">SMILES</th>
                    <th className="py-2 pr-3 text-right text-[#8B949E] font-medium">MW</th>
                    <th className="py-2 pr-3 text-right text-[#8B949E] font-medium">LogP</th>
                    <th className="py-2 pr-3 text-right text-[#8B949E] font-medium">HBD</th>
                    <th className="py-2 pr-3 text-right text-[#8B949E] font-medium">HBA</th>
                    <th className="py-2 pr-3 text-right text-[#8B949E] font-medium">Score</th>
                    <th className="py-2 pr-3 text-left text-[#8B949E] font-medium">Assessment</th>
                    <th className="py-2 text-right text-[#8B949E] font-medium">SA Score</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry, i) => (
                    <tr key={i} className="border-b border-[#2A2F3E]/50">
                      <td className="py-2 pr-3 text-[#FAFAFA]">{entry.name}</td>
                      <td className="py-2 pr-3 text-[#FAFAFA] font-mono text-xs max-w-[120px] truncate">
                        {entry.smiles}
                      </td>
                      {entry.status === 'pending' && <td colSpan={7} className="py-2 text-[#8B949E]">Pending</td>}
                      {entry.status === 'running' && (
                        <td colSpan={7} className="py-2">
                          <Loader2 className="h-4 w-4 animate-spin text-[#00D4AA]" />
                        </td>
                      )}
                      {entry.status === 'error' && (
                        <td colSpan={7} className="py-2 text-destructive text-xs">{entry.error}</td>
                      )}
                      {entry.status === 'done' && entry.result && (
                        <>
                          <td className="py-2 pr-3 text-right text-[#FAFAFA] font-mono">{formatNum(entry.result.mw)}</td>
                          <td className="py-2 pr-3 text-right text-[#FAFAFA] font-mono">{formatNum(entry.result.logp)}</td>
                          <td className="py-2 pr-3 text-right text-[#FAFAFA] font-mono">{formatNum(entry.result.hbd)}</td>
                          <td className="py-2 pr-3 text-right text-[#FAFAFA] font-mono">{formatNum(entry.result.hba)}</td>
                          <td className="py-2 pr-3 text-right text-[#FAFAFA] font-mono">{formatNum(entry.result.drug_likeness_score)}</td>
                          <td className="py-2 pr-3 text-[#FAFAFA]">{entry.result.assessment ?? 'N/A'}</td>
                          <td className="py-2 text-right text-[#FAFAFA] font-mono">{formatNum(entry.result.sa_score)}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {finishedEntries.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-[#FAFAFA]">Individual Radar Charts</h3>
          {entries.map((entry, i) => {
            if (!entry.result) return null
            const isOpen = expandedIdx === i
            return (
              <Card key={i} className="border-[#2A2F3E] bg-[#1A1F2E]">
                <button
                  onClick={() => setExpandedIdx(isOpen ? null : i)}
                  className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm text-[#FAFAFA] hover:bg-[#2A2F3E]/30"
                >
                  {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  {entry.name}
                </button>
                {isOpen && (
                  <CardContent>
                    <AdmetRadar admet={entry.result as unknown as Record<string, unknown>} compoundName={entry.name} />
                  </CardContent>
                )}
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}

function CompareTab() {
  const { data: compounds, isLoading } = useQuery({
    queryKey: ['compounds'],
    queryFn: async () => {
      const res = await apiGet<{ items: Compound[] }>('/api/compounds')
      return res.items ?? []
    },
  })

  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const toggleCompound = useCallback((id: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= 6) return prev
      return [...prev, id]
    })
  }, [])

  const selectedCompounds = (compounds ?? []).filter((c) => selectedIds.includes(c.id))

  const radarData = selectedCompounds
    .filter((c) => c.admet)
    .map((c) => ({
      name: c.name ?? c.smiles ?? c.id,
      admet: c.admet as Record<string, unknown>,
    }))

  return (
    <div className="space-y-6">
      <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
        <CardHeader>
          <CardTitle className="text-[#FAFAFA]">Select Compounds (up to 6)</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && (
            <div className="flex items-center gap-2 py-4">
              <Loader2 className="h-4 w-4 animate-spin text-[#00D4AA]" />
              <span className="text-sm text-[#8B949E]">Loading compounds...</span>
            </div>
          )}
          {compounds && compounds.length === 0 && (
            <p className="text-sm text-[#8B949E]">No compounds in database.</p>
          )}
          {compounds && compounds.length > 0 && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 max-h-64 overflow-y-auto">
              {compounds.map((c) => {
                const checked = selectedIds.includes(c.id)
                return (
                  <button
                    key={c.id}
                    onClick={() => toggleCompound(c.id)}
                    className={`flex items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                      checked
                        ? 'border-[#00D4AA] bg-[#00D4AA]/10 text-[#FAFAFA]'
                        : 'border-[#2A2F3E] text-[#8B949E] hover:border-[#8B949E]'
                    }`}
                  >
                    <div className={`h-3 w-3 rounded-sm border ${checked ? 'bg-[#00D4AA] border-[#00D4AA]' : 'border-[#8B949E]'}`} />
                    <span className="truncate">{c.name ?? c.smiles ?? c.id}</span>
                  </button>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {selectedCompounds.length >= 2 && (
        <>
          {radarData.length >= 2 && (
            <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
              <CardContent className="pt-4">
                <AdmetRadar compounds={radarData} />
              </CardContent>
            </Card>
          )}

          <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
            <CardHeader>
              <CardTitle className="text-[#FAFAFA]">Comparison Table</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#2A2F3E]">
                      <th className="py-2 pr-3 text-left text-[#8B949E] font-medium">Property</th>
                      {selectedCompounds.map((c) => (
                        <th key={c.id} className="py-2 pr-3 text-right text-[#8B949E] font-medium">
                          {c.name ?? 'Unknown'}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {PROPERTY_ROWS.map((row) => (
                      <tr key={row.key} className="border-b border-[#2A2F3E]/50">
                        <td className="py-2 pr-3 text-[#FAFAFA]">{row.label}</td>
                        {selectedCompounds.map((c) => {
                          const admet = c.admet as Record<string, unknown> | null
                          const val = admet ? (admet[row.key] as number | null) : null
                          return (
                            <td key={c.id} className="py-2 pr-3 text-right text-[#FAFAFA] font-mono">
                              {formatNum(val)}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {selectedCompounds.map((c) => (
              <MetricCard
                key={c.id}
                label={c.name ?? 'Unknown'}
                value={formatNum(c.drug_likeness_score)}
                delta={c.admet ? String((c.admet as Record<string, unknown>).assessment ?? '') : ''}
              />
            ))}
          </div>
        </>
      )}

      {selectedCompounds.length === 1 && (
        <p className="text-sm text-[#8B949E]">Select at least 2 compounds to compare.</p>
      )}
    </div>
  )
}

export default function AdmetPage() {
  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-[#FAFAFA]">ADMET Analysis</h1>
        <p className="mt-1 text-sm text-[#8B949E]">Drug-likeness screening and molecular property analysis</p>
      </div>

      <Tabs defaultValue="single">
        <TabsList>
          <TabsTrigger value="single">Single Compound</TabsTrigger>
          <TabsTrigger value="batch">Batch Mode</TabsTrigger>
          <TabsTrigger value="compare">Compare from Database</TabsTrigger>
        </TabsList>

        <TabsContent value="single">
          <SingleCompoundTab />
        </TabsContent>
        <TabsContent value="batch">
          <BatchModeTab />
        </TabsContent>
        <TabsContent value="compare">
          <CompareTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
