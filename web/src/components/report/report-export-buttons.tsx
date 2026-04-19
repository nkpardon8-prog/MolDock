'use client'

import { useState } from 'react'
import { apiDownload } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Download, Loader2 } from 'lucide-react'

async function triggerDownload(reportId: string, fmt: 'docx' | 'pdf') {
  const url = await apiDownload(`/api/reports/${reportId}/export?fmt=${fmt}`)
  const a = document.createElement('a')
  a.href = url
  a.download = `report-${reportId}.${fmt}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function ReportExportButtons({ reportId }: { reportId: string }) {
  const [busy, setBusy] = useState<'docx' | 'pdf' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handle(fmt: 'docx' | 'pdf') {
    setBusy(fmt)
    setError(null)
    try {
      await triggerDownload(reportId, fmt)
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to download ${fmt}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => handle('docx')}
          disabled={busy !== null}
          className="border-[#2A2F3E] text-[#FAFAFA]"
        >
          {busy === 'docx' ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Download className="mr-1 h-3 w-3" />}
          Download DOCX
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => handle('pdf')}
          disabled={busy !== null}
          className="border-[#2A2F3E] text-[#FAFAFA]"
        >
          {busy === 'pdf' ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Download className="mr-1 h-3 w-3" />}
          Download PDF
        </Button>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
