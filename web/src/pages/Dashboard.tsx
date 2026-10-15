import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../api'
import { Card, Empty, ErrorNote, Loading, ResultPill, Stat } from '../components/ui'

const RANGES = [
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
  { label: '1y', days: 365 },
  { label: 'All', days: undefined },
]

export default function Dashboard() {
  const [days, setDays] = useState<number | undefined>(90)
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<any>(null)

  useEffect(() => {
    setData(null)
    api.dashboard(days).then(setData).catch((e) => setErr(String(e)))
  }, [days])

  const timeClasses = useMemo(() => (data ? Object.keys(data.ratings) : []), [data])

  if (err) return <ErrorNote>{err}</ErrorNote>
  if (!data) return <Loading />

  const totals = data.totals

  if (totals.games === 0) {
    return (
      <Empty
        title="No games yet"
        hint={<>
          Connect a Chess.com account or upload a PGN to get started. {' '}
          <Link to="/onboarding" className="underline" style={{ color: 'var(--accent)' }}>Open onboarding</Link>.
        </>}
      />
    )
  }

  const perDay = Object.entries(data.activity.per_day).sort().map(([date, n]) => ({ date, n }))
  const perHour = Array.from({ length: 24 }, (_, h) => {
    const key = String(h).padStart(2, '0')
    return { hour: key, n: data.activity.per_hour[key] ?? 0 }
  })
  const perDow = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => ({ dow: d, n: data.activity.per_dow[d] ?? 0 }))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-bold">Dashboard</h1>
        <div className="ml-auto flex gap-1">
          {RANGES.map((r) => (
            <button key={r.label} className={`btn ${days === r.days ? 'btn-primary' : ''}`} onClick={() => setDays(r.days)}>
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Games" value={totals.games} sub={`${totals.wins}W / ${totals.draws}D / ${totals.losses}L`} />
        <Stat label="Win rate" value={`${totals.win_rate}%`} tone={totals.win_rate >= 50 ? 'good' : 'bad'} sub={`streak: ${data.streak.type ?? '–'} ${data.streak.length}`} />
        <Stat label="Analyzed" value={`${data.analysis.done}/${data.analysis.imported}`} sub={`${data.analysis.queued} queued · ${data.analysis.failed} failed`} />
        <Stat label="Avg ACPL" value={data.performance.avg_acpl ?? '–'} tone="warn" sub={data.performance.analyzed_games ? `${data.performance.analyzed_games} games analysed` : 'run an analysis'} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Rating progression">
          {timeClasses.length === 0 ? <div className="muted text-sm">No rated games in range.</div> : (
            <>
              <div className="mb-2 flex flex-wrap gap-2">
                {timeClasses.map((tc) => (
                  <span key={tc} className="chip">
                    {tc}: <b className="ml-1">{data.ratings[tc].current}</b>
                    <span className="ml-1" style={{ color: data.ratings[tc].change >= 0 ? '#86efac' : '#f87171' }}>
                      ({data.ratings[tc].change >= 0 ? '+' : ''}{data.ratings[tc].change})
                    </span>
                  </span>
                ))}
              </div>
              <div style={{ height: 200 }}>
                <ResponsiveContainer>
                  <LineChart data={mergeRatings(data.ratings)}>
                    <CartesianGrid stroke="#1f2841" strokeDasharray="3 3" />
                    <XAxis dataKey="i" tick={false} height={4} />
                    <YAxis tick={{ fill: '#93a0c4', fontSize: 10 }} domain={['auto', 'auto']} />
                    <Tooltip contentStyle={{ background: '#131a2c', border: '1px solid #27304f', borderRadius: 8 }} />
                    {timeClasses.map((tc, i) => (
                      <Line key={tc} type="monotone" dataKey={tc} dot={false} stroke={['#34d399', '#60a5fa', '#fbbf24', '#f472b6'][i % 4]} isAnimationActive={false} connectNulls />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </Card>

        <Card title="Games per day">
          <div style={{ height: 200 }}>
            <ResponsiveContainer>
              <BarChart data={perDay}>
                <CartesianGrid stroke="#1f2841" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fill: '#93a0c4', fontSize: 10 }} />
                <YAxis tick={{ fill: '#93a0c4', fontSize: 10 }} allowDecimals={false} />
                <Tooltip contentStyle={{ background: '#131a2c', border: '1px solid #27304f', borderRadius: 8 }} />
                <Bar dataKey="n" fill="#60a5fa" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="When you play (hour of day, UTC)">
          <div style={{ height: 160 }}>
            <ResponsiveContainer>
              <BarChart data={perHour}>
                <XAxis dataKey="hour" tick={{ fill: '#93a0c4', fontSize: 9 }} interval={2} />
                <YAxis tick={{ fill: '#93a0c4', fontSize: 10 }} allowDecimals={false} />
                <Tooltip contentStyle={{ background: '#131a2c', border: '1px solid #27304f', borderRadius: 8 }} />
                <Bar dataKey="n" fill="#34d399" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="By day of week">
          <div style={{ height: 160 }}>
            <ResponsiveContainer>
              <BarChart data={perDow}>
                <XAxis dataKey="dow" tick={{ fill: '#93a0c4', fontSize: 10 }} />
                <YAxis tick={{ fill: '#93a0c4', fontSize: 10 }} allowDecimals={false} />
                <Tooltip contentStyle={{ background: '#131a2c', border: '1px solid #27304f', borderRadius: 8 }} />
                <Bar dataKey="n" fill="#fbbf24" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Results by colour">
          <table className="data">
            <thead><tr><th>Colour</th><th>Games</th><th>Wins</th><th>Win rate</th></tr></thead>
            <tbody>
              {Object.entries(data.by_color).map(([c, v]: any) => (
                <tr key={c}><td>{c}</td><td>{v.games}</td><td>{v.wins}</td><td>{v.win_rate}%</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Results by opponent rating">
          <table className="data">
            <thead><tr><th>Band</th><th>Games</th><th>Win rate</th></tr></thead>
            <tbody>
              {Object.entries(data.opponent_bands).map(([b, v]: any) => (
                <tr key={b}><td>{b}</td><td>{v.games}</td><td>{v.win_rate}%</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Mistake profile (analysed)">
          <ul className="space-y-1 text-sm">
            <li className="flex justify-between"><span className="muted">Blunders / game</span><b>{data.performance.blunders_per_game ?? '–'}</b></li>
            <li className="flex justify-between"><span className="muted">Mistakes / game</span><b>{data.performance.mistakes_per_game ?? '–'}</b></li>
            <li className="flex justify-between"><span className="muted">Inaccuracies / game</span><b>{data.performance.inaccuracies_per_game ?? '–'}</b></li>
            <li className="flex justify-between"><span className="muted">Missed wins</span><b>{data.performance.missed_wins ?? '–'}</b></li>
            <li className="flex justify-between"><span className="muted">Time-pressure errors</span><b>{data.performance.time_pressure_errors ?? '–'}</b></li>
          </ul>
          <Link to="/training" className="btn btn-primary mt-3 inline-block">Build a training plan</Link>
        </Card>
      </div>

      <Card
        title="Recent games"
        right={<Link to="/games" className="btn">Open library</Link>}
      >
        <table className="data">
          <thead>
            <tr><th>Date</th><th>Opponent</th><th>Rating</th><th>Colour</th><th>Result</th><th>Opening</th><th>ACPL</th><th>??</th><th>Status</th></tr>
          </thead>
          <tbody>
            {data.recent_games.map((g: any) => (
              <tr key={g.id} onClick={() => (window.location.href = `/games/${g.id}`)}>
                <td>{g.end_time ? new Date(g.end_time).toLocaleDateString() : '–'}</td>
                <td>{g.opponent}</td>
                <td>{g.opponent_rating ?? '–'}</td>
                <td>{g.color}</td>
                <td><ResultPill result={g.result} /></td>
                <td className="max-w-[220px] truncate">{g.opening ?? '–'}</td>
                <td>{g.acpl ?? '–'}</td>
                <td>{g.blunders ?? 0}</td>
                <td><span className="chip">{g.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Ask your data">
        <div className="flex flex-wrap gap-2">
          <input
            className="input flex-1"
            style={{ minWidth: 240 }}
            placeholder="e.g. Why do I blunder more as black? What should I practise this week?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') api.assistant(question).then(setAnswer) }}
          />
          <button className="btn btn-primary" onClick={() => api.assistant(question).then(setAnswer)}>Ask</button>
        </div>
        {answer && (
          <div className="mt-3 text-sm">
            <p>{answer.answer}</p>
            {answer.insufficient && <p className="mt-1 muted">Insufficient evidence in the stored data.</p>}
            {answer.evidence?.length > 0 && (
              <details className="mt-2">
                <summary className="muted cursor-pointer">Evidence ({answer.evidence.length})</summary>
                <pre className="mt-2 overflow-auto text-[11px] muted">{JSON.stringify(answer.evidence, null, 2)}</pre>
              </details>
            )}
          </div>
        )}
        <div className="mt-2 text-[11px] muted">
          Answers are computed from your stored games and engine analysis only; numerical values are never invented.
        </div>
      </Card>
    </div>
  )
}

function mergeRatings(ratings: Record<string, any>): any[] {
  const maxLen = Math.max(...Object.values(ratings).map((r: any) => r.history.length), 0)
  const rows: any[] = []
  for (let i = 0; i < maxLen; i++) {
    const row: any = { i }
    for (const [tc, r] of Object.entries(ratings) as any) {
      if (r.history[i]) row[tc] = r.history[i].rating
    }
    rows.push(row)
  }
  return rows
}
