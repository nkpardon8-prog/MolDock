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
