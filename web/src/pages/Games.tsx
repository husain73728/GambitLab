import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type GameBrief } from '../api'
import { Card, ErrorNote, ResultPill } from '../components/ui'

const STATUS = ['', 'imported', 'queued', 'analyzing', 'done', 'failed']

export default function Games() {
  const nav = useNavigate()
  const [filters, setFilters] = useState<Record<string, any>>({ sort: 'date_desc', limit: 50 })
  const [data, setData] = useState<{ total: number; games: GameBrief[] } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = () => {
    api.games(filters).then(setData).catch((e) => setErr(String(e)))
  }
  useEffect(load, [filters])

  const set = (k: string, v: any) => setFilters((f) => ({ ...f, [k]: v }))

  const analyzeAll = async () => {
    setBusy(true)
    try {
      const pending = data?.games.filter((g) => g.status === 'imported' || g.status === 'failed') ?? []
      for (const g of pending) await api.analyze(g.id)
      load()
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-bold">My Games</h1>
        <span className="muted text-sm">{data ? `${data.total} games` : ''}</span>
        <button className="btn ml-auto" disabled={busy} onClick={analyzeAll}>
          {busy ? 'Queueing…' : 'Analyze this page'}
        </button>
      </div>

      {err && <ErrorNote>{err}</ErrorNote>}

      <Card title="Filters">
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <select className="input" value={filters.time_class ?? ''} onChange={(e) => set('time_class', e.target.value)}>
            <option value="">All time controls</option>
            {['bullet', 'blitz', 'rapid', 'daily'].map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className="input" value={filters.color ?? ''} onChange={(e) => set('color', e.target.value)}>
            <option value="">Any colour</option><option value="white">White</option><option value="black">Black</option>
          </select>
          <select className="input" value={filters.result ?? ''} onChange={(e) => set('result', e.target.value)}>
            <option value="">Any result</option><option value="win">Win</option><option value="loss">Loss</option><option value="draw">Draw</option>
          </select>
          <select className="input" value={filters.status ?? ''} onChange={(e) => set('status', e.target.value)}>
            {STATUS.map((s) => <option key={s} value={s}>{s || 'Any status'}</option>)}
          </select>
          <input className="input" placeholder="Opponent" value={filters.opponent ?? ''} onChange={(e) => set('opponent', e.target.value)} />
          <input className="input" placeholder="Opening / ECO" value={filters.opening ?? ''} onChange={(e) => set('opening', e.target.value)} />
          <input className="input" type="number" placeholder="Min opp rating" value={filters.min_opp_rating ?? ''} onChange={(e) => set('min_opp_rating', e.target.value)} />
          <input className="input" type="number" placeholder="Max opp rating" value={filters.max_opp_rating ?? ''} onChange={(e) => set('max_opp_rating', e.target.value)} />
          <input className="input" type="number" placeholder="Min blunders" value={filters.min_blunders ?? ''} onChange={(e) => set('min_blunders', e.target.value)} />
          <input className="input" placeholder="Termination (e.g. time)" value={filters.termination ?? ''} onChange={(e) => set('termination', e.target.value)} />
          <select className="input" value={filters.sort ?? 'date_desc'} onChange={(e) => set('sort', e.target.value)}>
            <option value="date_desc">Newest first</option><option value="date_asc">Oldest first</option>
            <option value="blunders">Most blunders</option><option value="acpl">Highest ACPL</option>
          </select>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!filters.has_missed_win} onChange={(e) => set('has_missed_win', e.target.checked)} />
            Missed a win
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!filters.has_time_pressure_error} onChange={(e) => set('has_time_pressure_error', e.target.checked)} />
            Time-pressure error
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!filters.favorite} onChange={(e) => set('favorite', e.target.checked)} />
            Favourites only
          </label>
        </div>
      </Card>

      <Card>
        <table className="data">
          <thead>
            <tr>
              <th>Date</th><th>Opponent</th><th>Ratings</th><th>Colour</th><th>Opening</th>
              <th>Time</th><th>Result</th><th>Moves</th><th>ACPL</th><th>Acc</th><th>??</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data?.games.map((g) => (
              <tr key={g.id} onClick={() => nav(`/games/${g.id}`)}>
                <td>{g.end_time ? new Date(g.end_time).toLocaleDateString() : '–'}</td>
                <td>{g.opponent ?? '–'}</td>
                <td className="text-xs muted">{g.player_rating ?? '?'} vs {g.opponent_rating ?? '?'}</td>
                <td>{g.color}</td>
                <td className="max-w-[240px] truncate" title={g.opening ?? ''}>{g.opening ?? '–'}</td>
                <td>{g.time_class ?? g.time_control ?? '–'}</td>
                <td><ResultPill result={g.result} /></td>
                <td>{g.moves}</td>
                <td>{g.acpl ?? '–'}</td>
                <td>{g.accuracy ?? '–'}</td>
                <td>{g.blunders ?? 0}/{g.mistakes ?? 0}</td>
                <td><span className={`chip ${g.status === 'done' ? 'cls-best' : g.status === 'failed' ? 'cls-blunder' : ''}`}>{g.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.games.length === 0 && <div className="p-4 muted text-sm">No games match these filters.</div>}
      </Card>
    </div>
  )
}
