'use client'

import dynamic from 'next/dynamic'

export const DynamicMol3DViewer = dynamic(
  () => import('./viewer'),
  {
    ssr: false,
    loading: () => (
      <div
        className="animate-pulse rounded-lg bg-card"
        style={{ width: 800, height: 600 }}
      />
    ),
  }
)
