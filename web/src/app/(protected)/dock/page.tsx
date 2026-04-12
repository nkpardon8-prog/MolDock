'use client'

import { useState, useCallback } from 'react'
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
import { FlaskConical } from 'lucide-react'

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
  const [compound, setCompound] = useState('')
  const [exhaustiveness, setExhaustiveness] = useState(32)
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const { status, progress, result, error } = useJobStream(jobId)

  const resultData = result as Record<string, unknown> | null
  const bestEnergy = resultData?.best_energy as number | undefined
  const allEnergies = resultData?.all_energies as number[] | undefined
  const admet = resultData?.admet as Record<string, unknown> | undefined
  const drugLikenessScore = resultData?.drug_likeness_score as number | undefined
  const saScore = resultData?.sa_score as number | undefined
  const outputPath = resultData?.output_path as string | undefined

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

  const files = outputPath
    ? [
        {
          name: outputPath.split('/').pop() || 'output.pdbqt',
          type: 'docked' as const,
          downloadUrl: `/api/files?path=${encodeURIComponent(outputPath)}`,
          path: outputPath,
        },
      ]
    : []

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
              <Label htmlFor="pdb-id" className="text-[#FAFAFA]">PDB ID</Label>
              <Input
                id="pdb-id"
                placeholder="e.g. 3S7S"
                maxLength={4}
                value={pdbId}
                onChange={(e) => setPdbId(e.target.value)}
                disabled={isRunning}
                className="border-[#2A2F3E] bg-[#0E1117] font-mono uppercase text-[#FAFAFA]"
              />
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
              label="Poses"
              value={allEnergies?.length ?? '--'}
            />
            <MetricCard
              label="Binding Quality"
              value={quality?.label ?? '--'}
              deltaColor={quality?.color}
            />
            <MetricCard
              label="Drug-likeness"
              value={drugLikenessScore != null ? drugLikenessScore.toFixed(2) : '--'}
            />
            <MetricCard
              label="SA Score"
              value={saScore != null ? saScore.toFixed(2) : '--'}
            />
          </div>

          {admet && (
            <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
              <CardContent className="pt-4">
                <AdmetRadar admet={admet} compoundName={compound} />
              </CardContent>
            </Card>
          )}

          {allEnergies && allEnergies.length > 0 && (
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
                        <th className="pb-2 font-medium">Energy (kcal/mol)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {allEnergies.map((energy, i) => {
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
