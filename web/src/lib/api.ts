const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { createClient } = await import('./supabase')
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.access_token) throw new Error('Not authenticated')
  return {
    Authorization: `Bearer ${session.access_token}`,
    'Content-Type': 'application/json',
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_URL}${path}`, { headers })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`GET ${path} failed (${res.status}): ${text}`)
  }
  return res.json()
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`POST ${path} failed (${res.status}): ${text}`)
  }
  return res.json()
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_URL}${path}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`PUT ${path} failed (${res.status}): ${text}`)
  }
  return res.json()
}

export async function apiDelete(path: string): Promise<void> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_URL}${path}`, {
    method: 'DELETE',
    headers,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`DELETE ${path} failed (${res.status}): ${text}`)
  }
}

export async function apiGetText(path: string): Promise<string> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_URL}${path}`, { headers })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`GET ${path} failed (${res.status}): ${text}`)
  }
  return res.text()
}

export async function apiDownload(path: string): Promise<string> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_URL}${path}`, { headers })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`DOWNLOAD ${path} failed (${res.status}): ${text}`)
  }
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

export function getStreamUrl(jobId: string): string {
  return `${API_URL}/api/jobs/${jobId}/stream`
}

export { API_URL }
