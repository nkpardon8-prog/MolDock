'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiPost } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { RunReport } from '@/lib/types'

export function ResearchQuestionEditor({ report }: { report: RunReport }) {
  const initial = report.research_question ?? ''
  const [draft, setDraft] = useState(initial)
  const qc = useQueryClient()

  const save = useMutation({
    mutationFn: () =>
      apiPost<RunReport>(`/api/reports/${report.id}/regenerate`, {
        sections: ['purpose', 'clinical_significance'],
        research_question: draft || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report'] })
    },
  })

  const disabled = save.isPending || draft === initial

  return (
    <div className="space-y-2 rounded-lg border border-[#2A2F3E] bg-[#0E1117] p-3">
      <label className="text-xs text-[#8B949E]">Research Question</label>
      <Textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="Optional research question to guide Purpose and Clinical Significance..."
        className="border-[#2A2F3E] bg-[#1A1F2E] text-[#FAFAFA]"
      />
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-[#8B949E]">
          Editing regenerates Purpose and Clinical Significance only.
        </p>
        <Button
          size="sm"
          onClick={() => save.mutate()}
          disabled={disabled}
          className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
        >
          {save.isPending ? 'Saving...' : 'Save'}
        </Button>
      </div>
      {save.isError && (
        <p className="text-xs text-red-400">
          {save.error instanceof Error ? save.error.message : 'Failed to save'}
        </p>
      )}
    </div>
  )
}
