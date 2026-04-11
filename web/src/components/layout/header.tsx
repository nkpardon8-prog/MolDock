'use client'

import { useEffect, useState } from 'react'
import { API_URL } from '@/lib/api'

export function Header({ title }: { title: string }) {
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false

    async function check() {
      try {
        const res = await fetch(`${API_URL}/api/health`, { cache: 'no-store' })
        if (!cancelled) setOnline(res.ok)
      } catch {
        if (!cancelled) setOnline(false)
      }
    }

    check()
    const id = setInterval(check, 30_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#2A2F3E] bg-[#1A1F2E] px-6">
      <h1 className="text-lg font-semibold text-[#FAFAFA]">{title}</h1>

      <div className="flex items-center gap-2 text-xs">
        {online === null ? (
          <span className="text-[#8B949E]">Checking backend...</span>
        ) : online ? (
          <>
            <span className="size-2 rounded-full bg-[#00D4AA]" />
            <span className="text-[#8B949E]">Backend online</span>
          </>
        ) : (
          <>
            <span className="size-2 rounded-full bg-destructive" />
            <span className="text-destructive">Backend offline</span>
          </>
        )}
      </div>
    </header>
  )
}
