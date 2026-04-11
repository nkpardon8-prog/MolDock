'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  LayoutDashboard,
  FlaskConical,
  Sparkles,
  Pill,
  BarChart3,
  Box,
  BookOpen,
  MessageSquare,
  LogOut,
  Menu,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV_SECTIONS = [
  {
    label: 'Overview',
    items: [
      { href: '/', icon: LayoutDashboard, label: 'Dashboard' },
    ],
  },
  {
    label: 'Workflows',
    items: [
      { href: '/dock', icon: FlaskConical, label: 'Dock' },
      { href: '/optimize', icon: Sparkles, label: 'Optimize' },
      { href: '/admet', icon: Pill, label: 'ADMET' },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { href: '/results', icon: BarChart3, label: 'Results' },
      { href: '/viewer', icon: Box, label: '3D Viewer' },
      { href: '/literature', icon: BookOpen, label: 'Literature' },
    ],
  },
  {
    label: 'AI Assistant',
    items: [
      { href: '/chat', icon: MessageSquare, label: 'Chat' },
    ],
  },
]

export function Sidebar() {
  const pathname = usePathname()
  const { user, signOut } = useAuth()
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        className="fixed top-3 left-3 z-50 rounded-md p-2 text-[#8B949E] hover:text-[#FAFAFA] md:hidden"
        onClick={() => setOpen(!open)}
      >
        {open ? <X className="size-5" /> : <Menu className="size-5" />}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-56 flex-col bg-[#1A1F2E] transition-transform md:static md:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-14 items-center px-4">
          <span className="text-lg font-bold text-[#00D4AA]">MoleCopilot</span>
        </div>

        <Separator className="bg-[#2A2F3E]" />

        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="mb-4">
              <span className="mb-1 block px-3 text-xs font-semibold uppercase tracking-wider text-[#8B949E]">
                {section.label}
              </span>
              {section.items.map((item) => {
                const active = pathname === item.href
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                      active
                        ? 'bg-[#00D4AA]/10 text-[#00D4AA]'
                        : 'text-[#8B949E] hover:bg-[#2A2F3E] hover:text-[#FAFAFA]',
                    )}
                  >
                    <item.icon className="size-4" />
                    {item.label}
                  </Link>
                )
              })}
            </div>
          ))}
        </nav>

        <Separator className="bg-[#2A2F3E]" />

        <div className="p-3">
          <p className="mb-2 truncate px-1 text-xs text-[#8B949E]">
            {user?.email}
          </p>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-2 text-[#8B949E] hover:text-[#FAFAFA]"
            onClick={() => signOut()}
          >
            <LogOut className="size-4" />
            Sign out
          </Button>
        </div>
      </aside>
    </>
  )
}
