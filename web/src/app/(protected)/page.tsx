'use client'

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import { apiGet } from '@/lib/api'
import type { StatsResponse, DockingRun, PaginatedResponse } from '@/lib/types'
import { MetricCard } from '@/components/metric-card'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { FlaskConical, Pill, BarChart3 } from 'lucide-react'

const EnergyBarChart = dynamic(
  () => import('@/components/charts/energy-bar-chart').then((m) => ({ default: m.EnergyBarChart })),
  { ssr: false },
)

function SkeletonCard() {
  return (
    <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
      <CardContent className="pt-4">
        <div className="h-3 w-16 animate-pulse rounded bg-zinc-700" />
        <div className="mt-2 h-7 w-24 animate-pulse rounded bg-zinc-700" />
      </CardContent>
    </Card>
  )
}

function SkeletonTable() {
  return (
    <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
      <CardHeader>
        <div className="h-5 w-40 animate-pulse rounded bg-zinc-700" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-4 w-full animate-pulse rounded bg-zinc-700" />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function energyColor(energy: number): string {
  if (energy < -8.0) return '#00D4AA'
  if (energy <= -7.0) return '#FFD700'
  return '#FF4B4B'
}

export default function DashboardPage() {
  const statsQuery = useQuery({
    queryKey: ['stats'],
    queryFn: () => apiGet<StatsResponse>('/api/stats'),
  })

  const runsQuery = useQuery({
    queryKey: ['recent-runs'],
    queryFn: () => apiGet<PaginatedResponse<DockingRun>>('/api/results?limit=10'),
  })

  const isLoading = statsQuery.isLoading || runsQuery.isLoading
  const isError = statsQuery.isError || runsQuery.isError

  if (isError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
        <p className="text-sm text-red-400">
          {statsQuery.error?.message || runsQuery.error?.message || 'Failed to load dashboard data'}
        </p>
        <Button
          variant="outline"
          className="border-zinc-600 text-zinc-300 hover:bg-zinc-800"
          onClick={() => {
            statsQuery.refetch()
            runsQuery.refetch()
          }}
        >
          Retry
        </Button>
      </div>
    )
  }

  const stats = statsQuery.data
  const runs = runsQuery.data?.items ?? []

  return (
    <div className="flex flex-col gap-6 p-6">
      <h1 className="text-xl font-bold text-[#FAFAFA]">Dashboard</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <MetricCard label="Proteins" value={stats?.total_proteins ?? 0} />
            <MetricCard label="Compounds" value={stats?.total_compounds ?? 0} />
            <MetricCard label="Docking Runs" value={stats?.total_runs ?? 0} />
            <MetricCard
              label="Best Energy"
              value={stats?.best_energy != null ? `${stats.best_energy.toFixed(1)} kcal/mol` : '--'}
              deltaColor={stats?.best_energy != null ? energyColor(stats.best_energy) : undefined}
            />
          </>
        )}
      </div>

      <div className="flex flex-wrap gap-3">
        <Link href="/dock">
          <Button className="gap-2 bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80">
            <FlaskConical className="size-4" />
            New Dock
          </Button>
        </Link>
        <Link href="/admet">
          <Button variant="outline" className="gap-2 border-zinc-600 text-zinc-300 hover:bg-zinc-800">
            <Pill className="size-4" />
            ADMET Check
          </Button>
        </Link>
        <Link href="/results">
          <Button variant="outline" className="gap-2 border-zinc-600 text-zinc-300 hover:bg-zinc-800">
            <BarChart3 className="size-4" />
            Browse Results
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <SkeletonTable />
      ) : (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardHeader>
            <CardTitle className="text-[#FAFAFA]">Recent Docking Runs</CardTitle>
          </CardHeader>
          <CardContent>
            {runs.length === 0 ? (
              <p className="text-sm text-[#8B949E]">No docking runs yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-[#2A2F3E] text-[#8B949E]">
                      <th className="pb-2 pr-4 font-medium">Protein</th>
                      <th className="pb-2 pr-4 font-medium">Compound</th>
                      <th className="pb-2 pr-4 font-medium">Energy (kcal/mol)</th>
                      <th className="pb-2 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((run) => (
                      <tr key={run.id} className="border-b border-[#2A2F3E]/50">
                        <td className="py-2 pr-4 font-mono text-[#FAFAFA]">
                          {run.proteins?.pdb_id ?? '--'}
                        </td>
                        <td className="py-2 pr-4 text-[#FAFAFA]">
                          {run.compounds?.name ?? '--'}
                        </td>
                        <td className="py-2 pr-4">
                          {run.best_energy != null ? (
                            <span style={{ color: energyColor(run.best_energy) }}>
                              {run.best_energy.toFixed(1)}
                            </span>
                          ) : (
                            '--'
                          )}
                        </td>
                        <td className="py-2 text-[#8B949E]">
                          {run.created_at
                            ? new Date(run.created_at).toLocaleDateString()
                            : '--'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {!isLoading && runs.length > 0 && (
        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <CardContent className="pt-4">
            <EnergyBarChart
              runs={runs.map((r) => ({
                compound_name: r.compounds?.name,
                best_energy: r.best_energy ?? 0,
              }))}
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
