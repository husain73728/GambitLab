import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Card, ErrorNote, Loading } from '../components/ui'

export default function Openings() {
  const [data, setData] = useState<any>(null)
  const [color, setColor] = useState('')
  const [repo, setRepo] = useState<any>(null)
  const [name, setName] = useState('')
  const [moves, setMoves] = useState('')
  const [repColor, setRepColor] = useState('white')
  const [err, setErr] = useState<string | null>(null)

  const load = () => {
    api.openings({ color: color || undefined }).then(setData).catch((e) => setErr(String(e)))
    api.repertoire().then(setRepo).catch(() => {})
  }
  useEffect(load, [color])

  if (err) return <ErrorNote>{err}</ErrorNote>
  if (!data) return <Loading />

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-bold">Openings</h1>
        <select className="input w-40" value={color} onChange={(e) => setColor(e.target.value)}>
          <option value="">Both colours</option><option value="white">As white</option><option value="black">As black</option>
        </select>
        <span className="text-xs muted ml-auto">{data.note}</span>
      </div>

      <Card title="Opening performance">
        <table className="data">
          <thead>
            <tr><th>Opening</th><th>ECO</th><th>Games</th><th>W/D/L</th><th>Win%</th><th>Score%</th>
              <th>Avg opp</th><th>ACPL</th></tr>
          </thead>
          <tbody>
            {data.openings.map((o: any) => (
              <tr key={o.opening} style={{ cursor: 'default' }}>
                <td title={o.opening}>{o.opening}{o.sample_warning && <span className="chip ml-2">small sample</span>}</td>
                <td>{o.eco ?? '–'}</td>
                <td>{o.games}</td>
                <td>{o.wins}/{o.draws}/{o.losses}</td>
                <td>{o.win_rate}%</td>
                <td><b>{o.score_rate}%</b></td>
                <td>{o.avg_opponent_rating ?? '–'}</td>
                <td>{o.avg_acpl ?? '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.openings.length === 0 && <div className="p-4 muted text-sm">No openings yet.</div>}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Repertoire">
          <div className="space-y-2">
            <input className="input" placeholder="Line name (e.g. Sicilian Najdorf)" value={name} onChange={(e) => setName(e.target.value)} />
            <div className="flex gap-2">
              <select className="input w-32" value={repColor} onChange={(e) => setRepColor(e.target.value)}>
                <option value="white">white</option><option value="black">black</option>
              </select>
              <input className="input" placeholder="moves as UCI separated by spaces: e2e4 c7c5 g1f3" value={moves} onChange={(e) => setMoves(e.target.value)} />
              <button className="btn btn-primary" disabled={!name || !moves}
                      onClick={() => api.addRepertoire({ name, color: repColor, moves_uci: moves.trim().split(/\s+/) }).then(() => { setName(''); setMoves(''); load() })}>
                Save
              </button>
            </div>
          </div>
          <ul className="mt-3 space-y-1 text-sm">
            {(repo?.lines ?? []).map((l: any) => (
              <li key={l.id} className="flex items-center gap-2">
                <span className="chip">{l.color}</span>
                <b>{l.name}</b>
                <span className="muted truncate">{l.moves_uci.join(' ')}</span>
                <button className="btn ml-auto" onClick={() => api.delRepertoire(l.id).then(load)}>Delete</button>
              </li>
            ))}
            {(repo?.lines ?? []).length === 0 && <li className="muted">No saved lines yet.</li>}
          </ul>
        </Card>

        <Card title="Preparation tips">
          <ul className="list-disc space-y-1 pl-5 text-sm">
            <li>Openings with a <b>small sample</b> badge are not conclusive — play more before judging them.</li>
            <li>Openings below ~45% score are worth preparing or avoiding.</li>
            <li>Open a game from <Link to="/games" className="underline" style={{ color: 'var(--accent)' }}>My Games</Link> and compare it to a saved repertoire line to find where you leave preparation.</li>
          </ul>
        </Card>
      </div>
    </div>
  )
}
