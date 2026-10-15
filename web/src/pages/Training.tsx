import { useEffect, useState } from 'react'
import { Chess } from 'chess.js'
import { api } from '../api'
import Board from '../components/Board'
import { Card, Empty, ErrorNote, Loading, Stat } from '../components/ui'

export default function Training() {
  const [plan, setPlan] = useState<any>(null)
  const [minutes, setMinutes] = useState(120)
  const [exercises, setExercises] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)
  const [current, setCurrent] = useState<any>(null)
  const [fen, setFen] = useState('')
  const [result, setResult] = useState<any>(null)
  const [hint, setHint] = useState(false)
  const [started, setStarted] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const load = () => {
    api.plan().then(setPlan).catch((e) => setErr(String(e)))
    api.exercises({ limit: 100 }).then((r) => setExercises(r.exercises)).catch(() => {})
    api.trainingStats().then(setStats).catch(() => {})
  }
  useEffect(load, [])

  const startExercise = (ex: any) => {
    setCurrent(ex); setFen(ex.fen); setResult(null); setHint(false); setStarted(Date.now())
  }

  const onDrop = ({ sourceSquare, targetSquare }: any) => {
    if (!targetSquare || !current) return false
    const chess = new Chess(fen)
    let move: any = null
    try {
      move = chess.move({ from: sourceSquare, to: targetSquare, promotion: 'q' })
    } catch { return false }
    if (!move) return false
    const uci = move.from + move.to + (move.promotion ?? '')
    setFen(chess.fen())
    api.attempt({ exercise_id: current.id, move_uci: uci, time_ms: Date.now() - started, hint })
      .then(setResult).catch((e) => setErr(String(e)))
    return true
  }

  if (err) return <ErrorNote>{err}</ErrorNote>
  if (!plan) return <Loading />

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-bold">Training plan</h1>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-sm muted">weekly budget</span>
          <input type="number" className="input w-24" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} />
          <span className="text-sm muted">min</span>
          <button className="btn" disabled={busy} onClick={async () => { setBusy(true); await api.generatePlan(minutes); load(); setBusy(false) }}>
            Rebuild plan
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="This week">
          {plan.plan ? (
            <>
              <div className="mb-2 text-sm muted">{plan.plan.summary}</div>
              <ul className="space-y-2">
                {plan.plan.items.map((i: any, idx: number) => (
                  <li key={idx} className="card p-3">
                    <div className="flex items-center gap-2">
                      <span className="chip">{i.minutes} min</span>
                      <b>{i.title}</b>
                      <span className="ml-auto text-xs muted">priority {i.priority}</span>
                    </div>
                    <div className="mt-1 text-sm muted">{i.reason || i.rationale}</div>
                  </li>
                ))}
              </ul>
            </>
          ) : <div className="muted text-sm">No plan yet — click “Rebuild plan”.</div>}
        </Card>

        <Card title="Detected weaknesses (with evidence)">
          <ul className="space-y-2">
            {plan.recommendations.map((r: any) => (
              <li key={r.id} className="text-sm">
                <div className="flex items-center gap-2">
                  <span className="chip">p {r.priority}</span><b>{r.title}</b>
                </div>
                <div className="muted">{r.reason}</div>
              </li>
            ))}
            {plan.recommendations.length === 0 && <li className="muted">Analyse more games to detect weaknesses.</li>}
          </ul>
        </Card>
      </div>

      <Card title="Puzzles from your own games"
            right={<button className="btn" disabled={busy} onClick={async () => { setBusy(true); await api.generatePuzzles(40); load(); setBusy(false) }}>Generate from mistakes</button>}>
        {stats && (
          <div className="mb-3 grid gap-3 sm:grid-cols-4">
            <Stat label="Exercises" value={stats.exercises} />
            <Stat label="Attempts" value={stats.attempts} />
            <Stat label="Solve rate" value={`${stats.solve_rate}%`} tone="good" />
            <Stat label="Due now" value={stats.due} />
          </div>
        )}
        {exercises.length === 0 ? (
          <Empty title="No exercises yet" hint="Generate puzzles from your analysed mistakes." />
        ) : (
          <table className="data">
            <thead><tr><th>FEN</th><th>Category</th><th>Motif</th><th>Difficulty</th><th>Tries</th><th>Solved</th><th></th></tr></thead>
            <tbody>
              {exercises.map((e) => (
                <tr key={e.id} style={{ cursor: 'default' }}>
                  <td className="max-w-[240px] truncate font-mono text-xs">{e.fen}</td>
                  <td>{e.category}</td>
                  <td>{e.motif ?? '–'}</td>
                  <td>{e.difficulty}</td>
                  <td>{e.attempts}</td>
                  <td>{e.solves}</td>
                  <td><button className="btn" onClick={() => startExercise(e)}>Solve</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {current && (
        <Card title={`Solving: ${current.category}${current.motif ? ` · ${current.motif}` : ''}`}
              right={<button className="btn" onClick={() => setCurrent(null)}>Close</button>}>
          <div className="grid gap-4 lg:grid-cols-[minmax(280px,420px)_1fr]">
            <Board fen={fen} orientation={current.side_to_move === 'white' ? 'white' : 'black'}
                   allowDragging onPieceDrop={onDrop} />
            <div className="space-y-2 text-sm">
              <p>{current.objective}</p>
              <p className="muted">You play {current.side_to_move}. Drag a piece to attempt the best move.</p>
              <div className="flex gap-2">
                <button className="btn" onClick={() => setHint(true)}>Hint (reveals solution)</button>
                <button className="btn" onClick={() => { setFen(current.fen); setResult(null); setStarted(Date.now()) }}>Reset</button>
              </div>
              {hint && <div className="chip">Hint: play {current.objective.includes('mate') ? 'the mating move' : 'the engine\'s best move'}</div>}
              {result && (
                <div className={`card p-3 ${result.correct ? 'cls-best' : 'cls-blunder'}`}>
                  <b>{result.correct ? 'Correct!' : 'Not the best move.'}</b>
                  <div className="mt-1">
                    Solution: <span className="font-mono">{result.solution}</span>
                    {result.accepted?.length > 1 && <> (also accepted: {result.accepted.slice(1).join(', ')})</>}
                  </div>
                  <div className="text-xs muted mt-1">{result.objective}</div>
                </div>
              )}
              <div className="text-xs muted">
                Engine suggestions are hidden while you solve, unless you press Hint.
              </div>
            </div>
          </div>
        </Card>
      )}

      <Card title="Training analytics">
        <pre className="overflow-auto text-xs muted">{JSON.stringify(stats?.by_category ?? {}, null, 2)}</pre>
        <p className="mt-2 text-xs muted">
          Each exercise is generated from one of your own games, its solution validated by the engine as a legal,
          best move at that position. Spaced review schedules harder/unseen topics sooner.
        </p>
      </Card>
    </div>
  )
}
