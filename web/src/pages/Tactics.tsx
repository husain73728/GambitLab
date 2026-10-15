import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Card, Empty, ErrorNote, Loading } from '../components/ui'

export default function Tactics() {
  const [data, setData] = useState<any>(null)
  const [breakdown, setBreakdown] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.tactics().then(setData).catch((e) => setErr(String(e)))
    api.breakdown().then(setBreakdown).catch(() => {})
  }, [])

  if (err) return <ErrorNote>{err}</ErrorNote>
  if (!data) return <Loading />

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Tactics</h1>

      {data.motifs.length === 0 ? (
        <Empty title="No tactical events detected yet"
               hint="Analyse some games and motif detection will run automatically on your mistakes." />
      ) : (
        <Card title="Recurring motifs">
          <table className="data">
            <thead>
              <tr><th>Motif</th><th>Missed</th><th>Found</th><th>Games</th><th>Avg loss</th>
                <th>Last 30d</th><th>Older</th><th>Examples</th></tr>
            </thead>
            <tbody>
              {data.motifs.map((m: any) => (
                <tr key={m.motif} style={{ cursor: 'default' }}>
                  <td className="capitalize">{m.label}</td>
                  <td><b style={{ color: '#f87171' }}>{m.missed}</b></td>
                  <td style={{ color: '#86efac' }}>{m.found}</td>
                  <td>{m.games_affected}</td>
                  <td>{m.avg_loss}cp</td>
                  <td>{m.recent30}</td>
                  <td>{m.historical}</td>
                  <td>
                    {m.examples.slice(0, 3).map((e: any, i: number) => (
                      <Link key={i} to={`/games/${e.game_id}`} className="chip mr-1" title={e.fen}>
                        game {e.game_id} · move {e.ply}
                      </Link>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs muted">
            Motifs are labelled only when verifiable from the board (forks, pins, skewers, discovered attacks,
            hanging pieces, back-rank mates) with a stored confidence. Uncertain motifs are not asserted.
          </p>
        </Card>
      )}

      {breakdown && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="By phase">
            <table className="data">
              <thead><tr><th>Phase</th><th>Moves</th><th>ACPL</th><th>?? /100</th></tr></thead>
              <tbody>
                {Object.entries(breakdown.by_phase).map(([k, v]: any) => (
                  <tr key={k} style={{ cursor: 'default' }}><td className="capitalize">{k}</td><td>{v.moves}</td><td>{v.acpl}</td><td>{v.blunders_per_100}</td></tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="By colour">
            <table className="data">
              <thead><tr><th>Colour</th><th>Moves</th><th>ACPL</th><th>?? /100</th></tr></thead>
              <tbody>
                {Object.entries(breakdown.by_color).map(([k, v]: any) => (
                  <tr key={k} style={{ cursor: 'default' }}><td>{k}</td><td>{v.moves}</td><td>{v.acpl}</td><td>{v.blunders_per_100}</td></tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="By opponent band">
            <table className="data">
              <thead><tr><th>Band</th><th>Moves</th><th>ACPL</th></tr></thead>
              <tbody>
                {Object.entries(breakdown.by_opponent_band).map(([k, v]: any) => (
                  <tr key={k} style={{ cursor: 'default' }}><td>{k}</td><td>{v.moves}</td><td>{v.acpl}</td></tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      <Card title="Detected weaknesses">
        <ul className="space-y-1 text-sm">
          {data.weaknesses.map((w: any, i: number) => (
            <li key={i} className="flex items-center gap-2">
              <span className="chip">priority {w.priority}</span>
              <b className="capitalize">{w.label}</b>
              <span className="muted">
                missed {w.missed} · {w.games_affected} games · avg {w.avg_loss}cp
              </span>
            </li>
          ))}
          {data.weaknesses.length === 0 && <li className="muted">None detected yet.</li>}
        </ul>
        <p className="mt-2 text-xs muted">
          Priority = 0.40·frequency + 0.30·avg loss + 0.15·games affected + 0.10·recency + 0.05·confidence (all normalised).
        </p>
      </Card>
    </div>
  )
}
