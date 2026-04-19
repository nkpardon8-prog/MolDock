'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import { apiGet, apiPost, apiDelete } from '@/lib/api'
import { useJobStream } from '@/components/jobs/use-job-stream'
import { MetricCard } from '@/components/metric-card'
import { AdmetRadar } from '@/components/charts/admet-radar'
import type { ChatSession, ChatMessage } from '@/lib/types'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Plus,
  Send,
  Trash2,
  MessageSquare,
  Loader2,
  Menu,
  X,
  FileText,
} from 'lucide-react'
import { RunReportPanel } from '@/components/report/run-report-panel'

interface LocalMessage {
  id: string
  role: string
  content: string
  artifacts?: Record<string, unknown> | null
}

const EXAMPLE_PROMPTS = [
  'Dock aspirin against aromatase (3S7S)',
  'Is CC(=O)Oc1ccccc1C(=O)O drug-like?',
  'Search PubMed for BACE1 marine natural products',
  'Compare aspirin, ibuprofen, and naproxen',
]

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<LocalMessage[]>([])
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const { status: streamStatus, progress, result: streamResult, error: streamError } = useJobStream(activeJobId)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  // Fetch sessions
  const fetchSessions = useCallback(async () => {
    setSessionsLoading(true)
    try {
      const data = await apiGet<ChatSession[]>('/api/chat/sessions')
      setSessions(data)
    } catch {
      // silent
    } finally {
      setSessionsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  // Load messages for a session
  async function loadSession(sessionId: string) {
    setActiveSessionId(sessionId)
    setMessagesLoading(true)
    setActiveJobId(null)
    setSendError(null)
    setDrawerOpen(false)
    setReportOpen(false)
    try {
      const data = await apiGet<ChatMessage[]>(`/api/chat/${sessionId}/messages`)
      setMessages(
        data.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          artifacts: m.artifacts,
        }))
      )
    } catch {
      setMessages([])
    } finally {
      setMessagesLoading(false)
    }
  }

  // New chat
  function startNewChat() {
    setActiveSessionId(null)
    setMessages([])
    setActiveJobId(null)
    setSendError(null)
    setDrawerOpen(false)
    setReportOpen(false)
    inputRef.current?.focus()
  }

  // Delete session
  async function deleteSession(sessionId: string) {
    try {
      await apiDelete(`/api/chat/sessions/${sessionId}`)
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
      if (activeSessionId === sessionId) {
        startNewChat()
      }
    } catch {
      // silent
    }
  }

  // Send message
  async function handleSend() {
    const text = inputText.trim()
    if (!text || sending) return

    setSending(true)
    setSendError(null)

    const tempId = `temp-${Date.now()}`
    const userMsg: LocalMessage = { id: tempId, role: 'user', content: text }
    setMessages((prev) => [...prev, userMsg])
    setInputText('')

    try {
      const body: Record<string, unknown> = { message: text }
      if (activeSessionId) body.session_id = activeSessionId

      const res = await apiPost<{ job_id: string; session_id: string }>('/api/chat/', body)

      if (!activeSessionId) {
        setActiveSessionId(res.session_id)
        fetchSessions()
      }

      setActiveJobId(res.job_id)
    } catch (err) {
      setSendError(err instanceof Error ? err.message : 'Failed to send message')
      setSending(false)
    }
  }

  // Handle stream completion
  useEffect(() => {
    if (streamStatus === 'complete' && streamResult) {
      const result = streamResult as Record<string, unknown>
      const content = String(result.response ?? result.text ?? result.content ?? '')
      const assistantMsg: LocalMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content,
        artifacts: result,
      }
      setMessages((prev) => [...prev, assistantMsg])
      setActiveJobId(null)
      setSending(false)
      fetchSessions()
    }
    if (streamStatus === 'error') {
      setSendError(streamError ?? 'Stream failed')
      setActiveJobId(null)
      setSending(false)
    }
  }, [streamStatus, streamResult, streamError, fetchSessions])

  // Auto scroll
  useEffect(() => {
    scrollToBottom()
  }, [messages, progress, scrollToBottom])

  const hasMessages = messages.length > 0 || activeJobId
  const hasUserMessage = messages.some((m) => m.role === 'user')
  const canGenerateReport = !!activeSessionId && hasUserMessage

  return (
    <div className="flex h-[calc(100vh-3.5rem)] overflow-hidden">
      {/* Mobile drawer toggle */}
      <button
        className="fixed bottom-20 right-4 z-50 rounded-full bg-[#1A1F2E] p-3 shadow-lg md:hidden"
        onClick={() => setDrawerOpen(!drawerOpen)}
      >
        {drawerOpen ? <X className="size-5 text-[#FAFAFA]" /> : <Menu className="size-5 text-[#FAFAFA]" />}
      </button>

      {/* Mobile backdrop */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      {/* Session sidebar */}
      <aside
        className={`${
          drawerOpen ? 'translate-x-0' : '-translate-x-full'
        } fixed inset-y-0 left-0 z-40 w-64 border-r border-[#2A2F3E] bg-[#1A1F2E] transition-transform md:static md:translate-x-0`}
      >
        <div className="flex h-full flex-col">
          <div className="p-3">
            <Button
              className="w-full bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
              onClick={startNewChat}
            >
              <Plus className="mr-2 size-4" />
              New Chat
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto px-2">
            {sessionsLoading ? (
              <div className="flex items-center gap-2 px-3 py-2 text-[#8B949E]">
                <Loader2 className="size-4 animate-spin" />
                <span className="text-sm">Loading...</span>
              </div>
            ) : sessions.length === 0 ? (
              <p className="px-3 py-2 text-sm text-[#8B949E]">No conversations yet.</p>
            ) : (
              <div className="space-y-1">
                {sessions.map((s) => (
                  <div
                    key={s.id}
                    className={`group flex items-center gap-2 rounded-md px-3 py-2 ${
                      activeSessionId === s.id
                        ? 'bg-[#00D4AA]/10 text-[#00D4AA]'
                        : 'text-[#8B949E] hover:bg-[#2A2F3E] hover:text-[#FAFAFA]'
                    }`}
                  >
                    <button
                      className="flex flex-1 items-center gap-2 truncate text-left text-sm"
                      onClick={() => loadSession(s.id)}
                    >
                      <MessageSquare className="size-4 shrink-0" />
                      <span className="truncate">{s.title ?? 'Untitled'}</span>
                    </button>
                    <span className="hidden text-xs group-hover:block">
                      {s.created_at ? new Date(s.created_at).toLocaleDateString() : ''}
                    </span>
                    <button
                      className="hidden shrink-0 text-[#8B949E] hover:text-red-400 group-hover:block"
                      onClick={(e) => {
                        e.stopPropagation()
                        deleteSession(s.id)
                      }}
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4">
          {!hasMessages ? (
            <EmptyState
              onSelect={(text) => {
                setInputText(text)
                inputRef.current?.focus()
              }}
            />
          ) : messagesLoading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-[#8B949E]">
              <Loader2 className="size-5 animate-spin" />
              Loading messages...
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-4">
              {canGenerateReport && (
                <div className="flex justify-end">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setReportOpen((v) => !v)}
                    className="border-[#2A2F3E] text-[#FAFAFA] gap-1.5"
                  >
                    <FileText className="size-3" />
                    {reportOpen ? 'Hide report' : 'Generate report for this session'}
                  </Button>
                </div>
              )}

              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}

              {/* Streaming indicator */}
              {activeJobId && streamStatus === 'connecting' && (
                <div className="flex items-start gap-3">
                  <div className="max-w-[80%] rounded-lg border border-[#2A2F3E] bg-[#1A1F2E] p-3">
                    <div className="flex items-center gap-2 text-[#8B949E]">
                      <Loader2 className="size-4 animate-spin" />
                      <span className="text-sm">Connecting...</span>
                    </div>
                  </div>
                </div>
              )}

              {activeJobId && streamStatus === 'streaming' && progress.text && (
                <div className="flex items-start gap-3">
                  <div className="max-w-[80%] rounded-lg border border-[#2A2F3E] bg-[#1A1F2E] p-3">
                    {progress.step && (
                      <p className="mb-1 text-xs font-medium text-[#00D4AA]">{progress.step}</p>
                    )}
                    <div className="prose prose-sm prose-invert max-w-none">
                      <ReactMarkdown>{progress.text}</ReactMarkdown>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <Loader2 className="size-3 animate-spin text-[#8B949E]" />
                      <span className="text-xs text-[#8B949E]">Thinking...</span>
                    </div>
                  </div>
                </div>
              )}

              {activeJobId && streamStatus === 'streaming' && !progress.text && progress.step && (
                <div className="flex items-start gap-3">
                  <div className="max-w-[80%] rounded-lg border border-[#2A2F3E] bg-[#1A1F2E] p-3">
                    <div className="flex items-center gap-2 text-[#8B949E]">
                      <Loader2 className="size-4 animate-spin text-[#00D4AA]" />
                      <span className="text-sm">{progress.step}</span>
                    </div>
                  </div>
                </div>
              )}

              {reportOpen && activeSessionId && (
                <RunReportPanel runId={activeSessionId} runType="chat_session" />
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Error */}
        {sendError && (
          <div className="mx-4 mb-2 rounded-lg border border-red-500/50 bg-red-950/30 p-3">
            <p className="text-sm text-red-400">{sendError}</p>
          </div>
        )}

        {/* Input area */}
        <div className="border-t border-[#2A2F3E] bg-[#0E1117] p-4">
          <div className="mx-auto flex max-w-3xl gap-2">
            <Input
              ref={inputRef}
              placeholder="Ask MoleCopilot anything..."
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              disabled={sending}
              className="border-[#2A2F3E] bg-[#1A1F2E] text-[#FAFAFA]"
            />
            <Button
              className="bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
              disabled={!inputText.trim() || sending}
              onClick={handleSend}
            >
              {sending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function EmptyState({ onSelect }: { onSelect: (text: string) => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-[#FAFAFA]">MoleCopilot</h2>
        <p className="mt-2 text-sm text-[#8B949E]">
          Your AI assistant for molecular docking and drug discovery
        </p>
      </div>
      <div className="grid w-full max-w-lg grid-cols-1 gap-3 sm:grid-cols-2">
        {EXAMPLE_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            className="rounded-lg border border-[#2A2F3E] bg-[#1A1F2E] px-4 py-3 text-left text-sm text-[#8B949E] transition-colors hover:border-[#00D4AA]/50 hover:text-[#FAFAFA]"
            onClick={() => onSelect(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  )
}

function MessageBubble({ message }: { message: LocalMessage }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-lg p-3 ${
          isUser
            ? 'bg-[#00D4AA]/20 text-[#FAFAFA]'
            : 'border border-[#2A2F3E] bg-[#1A1F2E] text-[#FAFAFA]'
        }`}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="space-y-3">
            <div className="prose prose-sm prose-invert max-w-none">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
            {message.artifacts && <ArtifactDisplay artifacts={message.artifacts} />}
          </div>
        )}
      </div>
    </div>
  )
}

function ArtifactDisplay({ artifacts }: { artifacts: Record<string, unknown> }) {
  const bestEnergy = artifacts.best_energy as number | undefined
  const allEnergies = artifacts.all_energies as number[] | undefined
  const admet = artifacts.admet as Record<string, unknown> | undefined
  const proteinName = String(artifacts.protein_name ?? artifacts.pdb_id ?? '')
  const compoundName = String(artifacts.compound_name ?? '')

  const hasDockingResult = bestEnergy != null
  const hasAdmet = admet != null && typeof admet === 'object'

  if (!hasDockingResult && !hasAdmet) return null

  return (
    <div className="space-y-3 pt-2">
      {hasDockingResult && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <MetricCard
            label="Best Energy"
            value={`${bestEnergy.toFixed(1)} kcal/mol`}
            delta={bestEnergy < -7.0 ? 'Promising' : 'Weak'}
            deltaColor={bestEnergy < -7.0 ? '#00D4AA' : '#FF4B4B'}
          />
          {proteinName && <MetricCard label="Protein" value={proteinName} />}
          {compoundName && <MetricCard label="Compound" value={compoundName} />}
          {allEnergies && allEnergies.length > 1 && (
            <MetricCard
              label="Poses"
              value={allEnergies.length}
              delta={`Range: ${Math.min(...allEnergies).toFixed(1)} to ${Math.max(...allEnergies).toFixed(1)}`}
            />
          )}
        </div>
      )}

      {hasAdmet && (
        <Card className="border-[#2A2F3E] bg-[#0E1117]">
          <CardContent className="pt-4">
            <AdmetRadar admet={admet as Record<string, unknown> & { [key: string]: unknown }} compoundName={compoundName || 'Compound'} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
