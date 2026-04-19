'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { RunReport, SectionKey } from '@/lib/types'

const SECTION_ORDER: { key: SectionKey; title: string }[] = [
  { key: 'purpose', title: 'Purpose' },
  { key: 'methods', title: 'Methods' },
  { key: 'what_it_did', title: 'What It Did' },
  { key: 'clinical_significance', title: 'Clinical Significance' },
  { key: 'notes', title: 'Additional Notes' },
]

export function RunReportView({ report }: { report: RunReport }) {
  return (
    <div className="space-y-4">
      {SECTION_ORDER.map(({ key, title }) => {
        const body = report.sections?.[key] ?? ''
        return (
          <Card key={key} className="border-[#2A2F3E] bg-[#0E1117]">
            <CardHeader>
              <CardTitle className="text-sm text-[#FAFAFA]">{title}</CardTitle>
            </CardHeader>
            <CardContent>
              {body.trim().length === 0 ? (
                <p className="text-sm text-[#8B949E] italic">No content for this section.</p>
              ) : (
                <div className="prose prose-sm prose-invert max-w-none text-[#FAFAFA] leading-relaxed">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
