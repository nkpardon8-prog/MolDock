'use client'

import { useState, useMemo } from 'react'
import dynamic from 'next/dynamic'
import { apiPost } from '@/lib/api'
import { useJobStream } from '@/components/jobs/use-job-stream'
import { JobProgress } from '@/components/jobs/job-progress'
import { MetricCard } from '@/components/metric-card'
import { AdmetRadar } from '@/components/charts/admet-radar'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ChevronDown, ChevronRight, Download } from 'lucide-react'

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false })

type PropertyName = 'qed' | 'plogp' | 'none'

interface Analog {
  smiles: string
  score: number | null
  sa_score: number | null
  assessment: string | null
  mw: number | null
  logp: number | null
  drug_likeness: number | null
  hbd?: number | null
  hba?: number | null
  rotatable_bonds?: number | null
  tpsa?: number | null
}

interface OptimizeResult {
  analogs: Analog[]
  seed?: {
    smiles: string
    mw?: number | null
    logp?: number | null
    hbd?: number | null
    hba?: number | null
    rotatable_bonds?: number | null
    tpsa?: number | null
    sa_score?: number | null
    drug_likeness?: number | null
  }
}

export default function OptimizePage() {
  const [compound, setCompound] = useState('')
  const [propertyName, setPropertyName] = useState<PropertyName>('qed')
  const [numMolecules, setNumMolecules] = useState(20)
  const [minSimilarity, setMinSimilarity] = useState(0.3)
  const [scaledRadius, setScaledRadius] = useState(1.0)
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [expandedAnalogs, setExpandedAnalogs] = useState<Set<number>>(new Set())

  const { status, progress, result, error: streamError } = useJobStream(jobId)

  const optimizeResult = (status === 'complete' && result) ? result as OptimizeResult : null

  const analogs = optimizeResult?.analogs ?? []
  const seed = optimizeResult?.seed ?? null

  const passingSA = useMemo(
    () => analogs.filter((a) => a.sa_score != null && a.sa_score <= 7).length,
    [analogs]
  )

  const bestScore = useMemo(() => {
    const scores = analogs.map((a) => a.score).filter((s): s is number => s != null)
    return scores.length > 0 ? Math.max(...scores) : null
  }, [analogs])

  const bestSA = useMemo(() => {
    const scores = analogs.map((a) => a.sa_score).filter((s): s is number => s != null)
    return scores.length > 0 ? Math.min(...scores) : null
  }, [analogs])

  async function handleSubmit() {
    if (!compound.trim()) {
      setFormError('Please enter a compound (SMILES or name)')
      return
    }
    setFormError(null)
    setSubmitting(true)
    setJobId(null)
    try {
      const body: Record<string, unknown> = {
        compound: compound.trim(),
        num_molecules: numMolecules,
        min_similarity: minSimilarity,
      }
      if (propertyName !== 'none') {
        body.property_name = propertyName
      } else {
        body.property_name = null
        body.scaled_radius = scaledRadius
      }
      const resp = await apiPost<{ job_id: string }>('/api/optimize', body)
      setJobId(resp.job_id)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to start optimization')
    } finally {
      setSubmitting(false)
    }
  }

  function toggleAnalog(index: number) {
    setExpandedAnalogs((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  function downloadCSV() {
    if (analogs.length === 0) return
    const headers = ['Rank', 'SMILES', 'Score', 'SA Score', 'Assessment', 'MW', 'LogP', 'Drug-Likeness']
    const rows = analogs.map((a, i) => [
      i + 1,
      a.smiles,
      a.score?.toFixed(3) ?? '',
      a.sa_score?.toFixed(2) ?? '',
      a.assessment ?? '',
      a.mw?.toFixed(1) ?? '',
      a.logp?.toFixed(2) ?? '',
      a.drug_likeness?.toFixed(3) ?? '',
    ])
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'optimize_results.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const radarCompounds = useMemo(() => {
    const items: Array<{ name: string; admet: Record<string, unknown> }> = []
    if (seed) {
      items.push({
        name: 'Seed',
        admet: {
          MW: seed.mw,
          LogP: seed.logp,
          HBD: seed.hbd,
          HBA: seed.hba,
          RotBonds: seed.rotatable_bonds,
          TPSA: seed.tpsa,
        },
      })
    }
    analogs.slice(0, 3).forEach((a, i) => {
      items.push({
        name: `Analog ${i + 1}`,
        admet: {
          MW: a.mw,
          LogP: a.logp,
          HBD: a.hbd,
          HBA: a.hba,
          RotBonds: a.rotatable_bonds,
          TPSA: a.tpsa,
        },
      })
    })
    return items
  }, [seed, analogs])

  const saBarData = useMemo(() => {
    const sorted = analogs
      .map((a, i) => ({ label: `Analog ${i + 1}`, sa: a.sa_score }))
      .filter((d): d is { label: string; sa: number } => d.sa != null)
      .sort((a, b) => a.sa - b.sa)

    return {
      y: sorted.map((d) => d.label),
      x: sorted.map((d) => d.sa),
      colors: sorted.map((d) =>
        d.sa <= 4 ? '#00D4AA' : d.sa <= 6 ? '#FFE66D' : '#FF6B6B'
      ),
    }
  }, [analogs])

  return (
    <div className="min-h-screen bg-[#0E1117] p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <h1 className="text-2xl font-bold text-[#00D4AA]">Optimize</h1>

        {/* Form */}
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardHeader>
            <CardTitle className="text-[#FAFAFA]">Compound Optimization</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-[#8B949E]">Compound (SMILES or name)</Label>
              <Input
                value={compound}
                onChange={(e) => setCompound(e.target.value)}
                placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O or aspirin"
                className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
              />
            </div>

            <div className="space-y-2">
              <Label className="text-[#8B949E]">Property</Label>
              <Select value={propertyName} onValueChange={(v) => setPropertyName(v as PropertyName)}>
                <SelectTrigger className="w-full border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-[#2A2F3E] bg-[#1A1F2E]">
                  <SelectItem value="qed" className="text-[#FAFAFA]">QED</SelectItem>
                  <SelectItem value="plogp" className="text-[#FAFAFA]">pLogP</SelectItem>
                  <SelectItem value="none" className="text-[#FAFAFA]">None (analog sampling)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-[#8B949E]">Num Molecules</Label>
                <span className="text-sm font-mono text-[#FAFAFA]">{numMolecules}</span>
              </div>
              <Slider
                value={[numMolecules]}
                onValueChange={(v) => setNumMolecules(Array.isArray(v) ? v[0] : v)}
                min={5}
                max={50}
                step={5}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-[#8B949E]">Min Similarity</Label>
                <span className="text-sm font-mono text-[#FAFAFA]">{minSimilarity.toFixed(2)}</span>
              </div>
              <Slider
                value={[minSimilarity]}
                onValueChange={(v) => setMinSimilarity(Array.isArray(v) ? v[0] : v)}
                min={0}
                max={0.7}
                step={0.05}
              />
            </div>

            {propertyName === 'none' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="text-[#8B949E]">Scaled Radius</Label>
                  <span className="text-sm font-mono text-[#FAFAFA]">{scaledRadius.toFixed(1)}</span>
                </div>
                <Slider
                  value={[scaledRadius]}
                  onValueChange={(v) => setScaledRadius(Array.isArray(v) ? v[0] : v)}
                  min={0.1}
                  max={5.0}
                  step={0.1}
                />
              </div>
            )}

            {formError && (
              <div className="rounded-md bg-red-950/30 border border-red-500/50 px-3 py-2 text-sm text-red-400">
                {formError}
              </div>
            )}

            <Button
              onClick={handleSubmit}
              disabled={submitting || status === 'streaming' || status === 'connecting'}
              className="w-full bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
            >
              {submitting ? 'Submitting...' : 'Optimize'}
            </Button>
          </CardContent>
        </Card>

        {/* SSE Progress */}
        {jobId && status !== 'complete' && (
          <JobProgress status={status} progress={progress} error={streamError} />
        )}

        {/* Results */}
        {optimizeResult && analogs.length > 0 && (
          <div className="space-y-6">
            {/* Metric Cards */}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <MetricCard label="Generated" value={analogs.length} />
              <MetricCard
                label="Passing SA Filter"
                value={passingSA}
                delta={`SA score <= 7`}
                deltaColor="#00D4AA"
              />
              <MetricCard
                label="Best Score"
                value={bestScore != null ? bestScore.toFixed(3) : 'N/A'}
              />
              <MetricCard
                label="Best SA Score"
                value={bestSA != null ? bestSA.toFixed(2) : 'N/A'}
                deltaColor={bestSA != null && bestSA <= 4 ? '#00D4AA' : '#FFE66D'}
              />
            </div>

            {/* Seed baseline */}
            {seed && (
              <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                <CardHeader>
                  <CardTitle className="text-[#FAFAFA]">Seed Compound</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="mb-2 font-mono text-xs text-[#8B949E] break-all">{seed.smiles}</p>
                  <div className="grid grid-cols-3 gap-3 text-sm lg:grid-cols-6">
                    <div>
                      <span className="text-[#8B949E]">MW: </span>
                      <span className="text-[#FAFAFA]">{seed.mw?.toFixed(1) ?? 'N/A'}</span>
                    </div>
                    <div>
                      <span className="text-[#8B949E]">LogP: </span>
                      <span className="text-[#FAFAFA]">{seed.logp?.toFixed(2) ?? 'N/A'}</span>
                    </div>
                    <div>
                      <span className="text-[#8B949E]">HBD: </span>
                      <span className="text-[#FAFAFA]">{seed.hbd ?? 'N/A'}</span>
                    </div>
                    <div>
                      <span className="text-[#8B949E]">HBA: </span>
                      <span className="text-[#FAFAFA]">{seed.hba ?? 'N/A'}</span>
                    </div>
                    <div>
                      <span className="text-[#8B949E]">RotBonds: </span>
                      <span className="text-[#FAFAFA]">{seed.rotatable_bonds ?? 'N/A'}</span>
                    </div>
                    <div>
                      <span className="text-[#8B949E]">SA: </span>
                      <span className="text-[#FAFAFA]">{seed.sa_score?.toFixed(2) ?? 'N/A'}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Analogs Table */}
            <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-[#FAFAFA]">Analogs</CardTitle>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={downloadCSV}
                  className="border-[#2A2F3E] text-[#FAFAFA]"
                >
                  <Download className="mr-1 h-3 w-3" />
                  CSV
                </Button>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#2A2F3E] text-[#8B949E]">
                        <th className="px-2 py-2 text-left">Rank</th>
                        <th className="px-2 py-2 text-left">SMILES</th>
                        <th className="px-2 py-2 text-right">Score</th>
                        <th className="px-2 py-2 text-right">SA Score</th>
                        <th className="px-2 py-2 text-left">Assessment</th>
                        <th className="px-2 py-2 text-right">MW</th>
                        <th className="px-2 py-2 text-right">LogP</th>
                        <th className="px-2 py-2 text-right">Drug-Likeness</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analogs.map((a, i) => (
                        <tr
                          key={i}
                          className="border-b border-[#2A2F3E]/50 hover:bg-[#2A2F3E]/20"
                        >
                          <td className="px-2 py-2 text-[#FAFAFA]">{i + 1}</td>
                          <td className="max-w-[200px] truncate px-2 py-2 font-mono text-xs text-[#8B949E]">
                            {a.smiles}
                          </td>
                          <td className="px-2 py-2 text-right text-[#FAFAFA]">
                            {a.score?.toFixed(3) ?? 'N/A'}
                          </td>
                          <td className="px-2 py-2 text-right">
                            <span
                              className={
                                a.sa_score != null && a.sa_score <= 4
                                  ? 'text-[#00D4AA]'
                                  : a.sa_score != null && a.sa_score <= 6
                                    ? 'text-[#FFE66D]'
                                    : 'text-[#FF6B6B]'
                              }
                            >
                              {a.sa_score?.toFixed(2) ?? 'N/A'}
                            </span>
                          </td>
                          <td className="px-2 py-2 text-[#8B949E]">{a.assessment ?? '-'}</td>
                          <td className="px-2 py-2 text-right text-[#FAFAFA]">
                            {a.mw?.toFixed(1) ?? 'N/A'}
                          </td>
                          <td className="px-2 py-2 text-right text-[#FAFAFA]">
                            {a.logp?.toFixed(2) ?? 'N/A'}
                          </td>
                          <td className="px-2 py-2 text-right text-[#FAFAFA]">
                            {a.drug_likeness?.toFixed(3) ?? 'N/A'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            {/* Charts */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {radarCompounds.length > 0 && (
                <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                  <CardContent className="pt-4">
                    <AdmetRadar compounds={radarCompounds} />
                  </CardContent>
                </Card>
              )}

              {saBarData.x.length > 0 && (
                <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
                  <CardContent className="pt-4">
                    <Plot
                      data={[
                        {
                          type: 'bar',
                          orientation: 'h',
                          y: saBarData.y,
                          x: saBarData.x,
                          marker: { color: saBarData.colors },
                          hovertemplate: '%{y}: SA = %{x:.2f}<extra></extra>',
                        },
                      ]}
                      layout={{
                        title: { text: 'SA Scores', font: { size: 14, color: '#FAFAFA' } },
                        xaxis: {
                          title: { text: 'SA Score' },
                          gridcolor: 'rgba(255,255,255,0.1)',
                          color: '#FAFAFA',
                        },
                        yaxis: {
                          automargin: true,
                          color: '#FAFAFA',
                        },
                        paper_bgcolor: 'rgba(0,0,0,0)',
                        plot_bgcolor: 'rgba(0,0,0,0)',
                        font: { color: '#FAFAFA', family: 'sans-serif' },
                        margin: { l: 80, r: 20, t: 40, b: 40 },
                        height: 450,
                      }}
                      config={{ responsive: true }}
                      style={{ width: '100%' }}
                      useResizeHandler
                    />
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Individual Analog Details */}
            <div className="space-y-2">
              <h2 className="text-sm font-medium text-[#8B949E]">Analog Details</h2>
              {analogs.map((a, i) => (
                <Card key={i} className="border-[#2A2F3E] bg-[#1A1F2E]">
                  <button
                    onClick={() => toggleAnalog(i)}
                    className="flex w-full items-center justify-between px-4 py-3 text-left"
                  >
                    <span className="text-sm font-medium text-[#FAFAFA]">
                      Analog {i + 1}
                      <span className="ml-2 text-[#8B949E]">
                        Score: {a.score?.toFixed(3) ?? 'N/A'} | SA: {a.sa_score?.toFixed(2) ?? 'N/A'}
                      </span>
                    </span>
                    {expandedAnalogs.has(i)
                      ? <ChevronDown className="h-4 w-4 text-[#8B949E]" />
                      : <ChevronRight className="h-4 w-4 text-[#8B949E]" />}
                  </button>
                  {expandedAnalogs.has(i) && (
                    <CardContent className="border-t border-[#2A2F3E] pt-3">
                      <p className="mb-3 font-mono text-xs text-[#8B949E] break-all">{a.smiles}</p>
                      <div className="grid grid-cols-3 gap-3 text-sm lg:grid-cols-4">
                        <div>
                          <span className="text-[#8B949E]">Score: </span>
                          <span className="text-[#FAFAFA]">{a.score?.toFixed(3) ?? 'N/A'}</span>
                        </div>
                        <div>
                          <span className="text-[#8B949E]">SA Score: </span>
                          <span
                            className={
                              a.sa_score != null && a.sa_score <= 4
                                ? 'text-[#00D4AA]'
                                : a.sa_score != null && a.sa_score <= 6
                                  ? 'text-[#FFE66D]'
                                  : 'text-[#FF6B6B]'
                            }
                          >
                            {a.sa_score?.toFixed(2) ?? 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-[#8B949E]">Assessment: </span>
                          <span className="text-[#FAFAFA]">{a.assessment ?? '-'}</span>
                        </div>
                        <div>
                          <span className="text-[#8B949E]">MW: </span>
                          <span className="text-[#FAFAFA]">{a.mw?.toFixed(1) ?? 'N/A'}</span>
                        </div>
                        <div>
                          <span className="text-[#8B949E]">LogP: </span>
                          <span className="text-[#FAFAFA]">{a.logp?.toFixed(2) ?? 'N/A'}</span>
                        </div>
                        <div>
                          <span className="text-[#8B949E]">Drug-Likeness: </span>
                          <span className="text-[#FAFAFA]">{a.drug_likeness?.toFixed(3) ?? 'N/A'}</span>
                        </div>
                      </div>
                    </CardContent>
                  )}
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
