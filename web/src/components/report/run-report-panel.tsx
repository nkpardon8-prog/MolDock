'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '@/lib/api'
import { ChevronDown, ChevronRight, FileText, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { RunReportView } from './run-report-view'
import { ResearchQuestionEditor } from './research-question-editor'
import { ReportExportButtons } from './report-export-buttons'
import type { RunReport, RunType } from '@/lib/types'

type Props =
  | { runId: string; runType: RunType; reportId?: never }
  | { reportId: string; runId?: never; runType?: never }

function isByRun(p: Props): p is { runId: string; runType: RunType; reportId?: never } {
  return 'runId' in p && typeof p.runId === 'string'
}

export function RunReportPanel(props: Props) {
  const [open, setOpen] = useState(false)
  const [draftQuestion, setDraftQuestion] = useState('')
  const qc = useQueryClient()

  const byRun = isByRun(props)
  const runId = byRun ? props.runId : null
  const runType = byRun ? props.runType : null
  const reportId = !byRun ? props.reportId : null

  const queryKey: readonly unknown[] = byRun
    ? ['report', 'by-run', runId, runType]
    : ['report', 'by-id', reportId]

  const { data, isLoading, error, isFetching } = useQuery<RunReport | null>({
    queryKey,
    queryFn: async () => {
      try {
        if (byRun && runId && runType) {
          return await apiGet<RunReport>(
            `/api/reports/by-run/${runId}?run_type=${runType}`,
          )
        }
        return await apiGet<RunReport>(`/api/reports/${reportId}`)
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : ''
        if (msg.includes('404')) return null
        throw e
      }
    },
    enabled: open,
  })

  const generate = useMutation({
    mutationFn: () => {
      if (!byRun || !runId || !runType) {
        throw new Error('Cannot generate without runId/runType')
      }
      return apiPost<RunReport>('/api/reports/generate', {
        run_id: runId,
        run_type: runType,
        research_question: draftQuestion || null,
      })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  return (
    <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
      <CardHeader
        className="cursor-pointer select-none"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-2">
          {open
            ? <ChevronDown className="h-4 w-4 text-[#8B949E]" />
            : <ChevronRight className="h-4 w-4 text-[#8B949E]" />}
          <FileText className="h-4 w-4 text-[#8B949E]" />
          <CardTitle className="text-sm text-[#FAFAFA]">Run Report</CardTitle>
          {data && (
            <span className="ml-2 text-xs text-[#8B949E] truncate">
              {data.display_title}
            </span>
          )}
        </div>
      </CardHeader>
      {open && (
        <CardContent>
          {(isLoading || isFetching) && !data && (
            <div className="flex items-center gap-2 text-sm text-[#8B949E]">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading report...
            </div>
          )}

          {!isLoading && error && (
            <p className="text-sm text-red-400">
              {error instanceof Error ? error.message : 'Failed to load report'}
            </p>
          )}

          {!isLoading && !error && !data && byRun && (
            <div className="space-y-3">
              <p className="text-sm text-[#8B949E]">
                No report yet. Optionally add a research question to guide interpretation.
              </p>
              <Textarea
                placeholder="Research question (optional)"
                value={draftQuestion}
                onChange={(e) => setDraftQuestion(e.target.value)}
                className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
              />
              {generate.isError && (
                <p className="text-xs text-red-400">
                  {generate.error instanceof Error ? generate.error.message : 'Failed to generate'}
                </p>
              )}
              <Button
                onClick={() => generate.mutate()}
                disabled={generate.isPending}
                className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
              >
                {generate.isPending ? 'Generating...' : 'Generate Report'}
              </Button>
            </div>
          )}

          {!isLoading && !error && !data && !byRun && (
            <p className="text-sm text-red-400">Report not found.</p>
          )}

          {data && (
            <div className="space-y-4">
              <ResearchQuestionEditor report={data} />
              <RunReportView report={data} />
              <ReportExportButtons reportId={data.id} />
            </div>
          )}
        </CardContent>
      )}
    </Card>
  )
}
