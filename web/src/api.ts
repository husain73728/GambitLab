// Minimal typed API client for the GambitLab backend.

export interface Account {
  id: number
  provider: string
  username: string
  name?: string | null
  avatar?: string | null
  title?: string | null
  status?: string | null
  last_synced_at?: string | null
  stats?: any
}

export interface GameBrief {
  id: number
  end_time?: string | null
  opponent?: string | null
  opponent_rating?: number | null
  player_rating?: number | null
  color?: string | null
  result?: string | null
  time_class?: string | null
  time_control?: string | null
  opening?: string | null
  eco?: string | null
  termination?: string | null
  moves?: number
  status: string
  progress?: number
  acpl?: number | null
  accuracy?: number | null
  blunders?: number
  mistakes?: number
  inaccuracies?: number
  missed_wins?: number
  tactical_events?: number
  favorite?: boolean
}

export interface Move {
  ply: number
  move_number: number
  color: string
  san: string
  uci: string
  fen_before: string
  fen_after: string
  is_capture: boolean
  captured_piece?: string | null
  is_check: boolean
  is_mate: boolean
  clock?: number | null
  think?: number | null
  eval_cp?: number | null
  eval_mate_in?: number | null
  best_uci?: string | null
  best_eval_cp?: number | null
  best_mate_in?: number | null
  cp_loss?: number | null
  classification?: string | null
  provisional?: boolean
  alternatives?: { rank: number; uci: string; cp?: number | null; mate?: number | null; pv: string[] }[]
  explanation?: string | null
  material?: { white: number; black: number; diff: number }
}

export interface GameDetail {
  game: GameBrief & Record<string, any>
  moves: Move[]
  annotations: { ply?: number | null; comment?: string | null; tags?: string[]; kind: string }[]
  tactics: { ply: number; motif: string; kind: string; loss: number; confidence: number; detail: any }[]
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch { /* ignore */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

export const api = {
  me: () => req<{ user: any; account: Account | null }>('/api/me'),
  health: () => req<any>('/api/health'),
  preview: (username: string) =>
    req<any>(`/api/onboard/preview?username=${encodeURIComponent(username)}`),
  onboard: (username: string) =>
    req<any>('/api/onboard', { method: 'POST', body: JSON.stringify({ username }) }),
  importChesscom: (body: { months?: number | null; time_classes?: string[] | null; all_history?: boolean }) =>
    req<any>('/api/import/chesscom', { method: 'POST', body: JSON.stringify(body) }),
  importPgn: (pgn: string, username?: string) =>
    req<{ imported: number; skipped: number }>('/api/import/pgn', {
      method: 'POST', body: JSON.stringify({ pgn, username }),
    }),
  importLogs: () => req<{ logs: any[] }>('/api/import/logs'),
  dashboard: (days?: number) => req<any>(`/api/dashboard${days ? `?days=${days}` : ''}`),
  progress: (window = 50) => req<any>(`/api/progress?window=${window}`),
  games: (params: Record<string, any> = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
    })
    return req<{ total: number; games: GameBrief[] }>(`/api/games?${q.toString()}`)
  },
  game: (id: number) => req<GameDetail>(`/api/games/${id}`),
  analyze: (id: number) => req<any>(`/api/games/${id}/analyze`, { method: 'POST' }),
  setFavorite: (id: number, value: boolean) =>
    req<any>(`/api/games/${id}/favorite`, { method: 'POST', body: JSON.stringify({ value }) }),
  setNotes: (id: number, notes: string) =>
    req<any>(`/api/games/${id}/notes`, { method: 'POST', body: JSON.stringify({ notes }) }),
  annotate: (id: number, body: any) =>
    req<any>(`/api/games/${id}/annotations`, { method: 'POST', body: JSON.stringify(body) }),
  pgn: (id: number, annotated = true) =>
    req<{ pgn: string }>(`/api/games/${id}/pgn?annotated=${annotated}`),
  analysisStatus: () => req<any>('/api/analysis/status'),
  cancelJob: (id: number) => req<any>(`/api/analysis/${id}/cancel`, { method: 'POST' }),
  openings: (params: Record<string, any> = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v != null && v !== '' && q.set(k, String(v)))
    return req<any>(`/api/openings?${q}`)
  },
  compareRepertoire: (id: number) => req<any>(`/api/openings/compare/${id}`),
  breakdown: (days?: number) => req<any>(`/api/breakdown${days ? `?days=${days}` : ''}`),
  tactics: (days?: number) => req<any>(`/api/tactics${days ? `?days=${days}` : ''}`),
  clock: (days?: number) => req<any>(`/api/clock${days ? `?days=${days}` : ''}`),
  weaknesses: () => req<any>('/api/training/weaknesses'),
  plan: () => req<any>('/api/training/plan'),
  generatePlan: (minutes: number) =>
    req<any>('/api/training/plan/generate', { method: 'POST', body: JSON.stringify({ minutes }) }),
  generatePuzzles: (limit: number) =>
    req<any>('/api/training/exercises/generate', { method: 'POST', body: JSON.stringify({ limit }) }),
  exercises: (params: Record<string, any> = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v != null && v !== '' && q.set(k, String(v)))
    return req<{ exercises: any[] }>(`/api/training/exercises?${q}`)
  },
  attempt: (body: { exercise_id: number; move_uci: string; time_ms?: number; hint?: boolean }) =>
    req<any>('/api/training/attempt', { method: 'POST', body: JSON.stringify(body) }),
  trainingStats: () => req<any>('/api/training/stats'),
  repertoire: () => req<any>('/api/repertoire'),
  addRepertoire: (body: any) => req<any>('/api/repertoire', { method: 'POST', body: JSON.stringify(body) }),
  delRepertoire: (id: number) => req<any>(`/api/repertoire/${id}`, { method: 'DELETE' }),
  assistant: (q: string) => req<any>(`/api/assistant?q=${encodeURIComponent(q)}`),
  engineSettings: () => req<any>('/api/settings/engine'),
  updateEngine: (body: any) => req<any>('/api/settings/engine', { method: 'POST', body: JSON.stringify(body) }),
  probeEngine: () => req<any>('/api/settings/engine/probe', { method: 'POST' }),
}
