import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import type { Arrow } from 'react-chessboard'
import { api, type GameDetail } from '../api'
import Board from '../components/Board'
import { ClassificationLegend, EvalBar, EvalGraph, EvalTag, MoveList } from '../components/analysis'
import { Card, ErrorNote, Loading, ResultPill } from '../components/ui'
import {
  CLASSIFICATION_LABEL, evalToPercent, formatEval, materialFromFen, uciSquares,
} from '../lib/chess'

export default function GameAnalysis() {
  const { id } = useParams()
  const gameId = Number(id)
  const [detail, setDetail] = useState<GameDetail | null>(null)
  const [ply, setPly] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [noteSaved, setNoteSaved] = useState(false)
  const [runId, setRunId] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      const d = await api.game(gameId)
      setDetail(d)
      setNotes(d.game.notes ?? '')
      setPly((p) => (p === 0 ? Math.min(0, d.moves.length) : p))
    } catch (e) { setErr(String(e)) }
  }, [gameId])

  useEffect(() => { load() }, [load])

  const moves = detail?.moves ?? []
  const total = moves.length

  // Poll while analysis is running.
  useEffect(() => {
    if (!detail) return
    const status = detail.game.status
    if (status === 'queued' || status === 'analyzing') {
      const t = setInterval(load, 2500)
      return () => clearInterval(t)
    }
  }, [detail, load])

  const step = useCallback((delta: number) => {
    setPly((p) => Math.max(0, Math.min(total, p + delta)))
  }, [total])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') { e.preventDefault(); step(1) }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1) }
      else if (e.key === 'Home') { e.preventDefault(); setPly(0) }
      else if (e.key === 'End') { e.preventDefault(); setPly(total) }
      else if (e.key === 'f') setFlipped((f) => !f)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [step, total])

  const fen = ply === 0 ? moves[0]?.fen_before ?? '' : moves[ply - 1]?.fen_after ?? ''
  const current = ply >= 1 ? moves[ply - 1] : undefined

  const evalCp = ply === 0 ? moves[0]?.best_eval_cp ?? null : current?.eval_cp ?? null
  const evalMate = ply === 0 ? moves[0]?.best_mate_in ?? null : current?.eval_mate_in ?? null

  const arrows = useMemo<Arrow[]>(() => {
    if (!current) return []
    const out: Arrow[] = []
    const played = uciSquares(current.uci)
    if (played) out.push({ startSquare: played.from, endSquare: played.to, color: '#60a5fa' })
    if (current.best_uci && current.best_uci !== current.uci) {
      const best = uciSquares(current.best_uci)
      if (best) out.push({ startSquare: best.from, endSquare: best.to, color: '#34d399' })
    }
    return out
  }, [current])

  const squareStyles = useMemo<Record<string, React.CSSProperties>>(() => {
    if (!current) return {}
    const s: Record<string, React.CSSProperties> = {}
    const from = uciSquares(current.uci)
    if (from) {
      s[from.from] = { background: 'rgba(96,165,250,0.35)' }
      s[from.to] = { background: 'rgba(96,165,250,0.45)' }
    }
    return s
  }, [current])

  const material = useMemo(() => (fen ? materialFromFen(fen) : null), [fen])

  if (err) return <ErrorNote>{err}</ErrorNote>
  if (!detail) return <Loading label="Loading game…" />

  const g = detail.game as any
  const tacticsHere = detail.tactics.filter((t) => t.ply === ply)

  const runAnalysis = async () => {
    const r = await api.analyze(gameId)
    setRunId(r.job_id)
    setTimeout(load, 800)
  }

  const downloadPgn = async () => {
    const { pgn } = await api.pgn(gameId, true)
    const blob = new Blob([pgn], { type: 'application/x-chess-pgn' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `gambitlab-game-${gameId}.pgn`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">
          {g.white} ({g.white_rating ?? '?'}) vs {g.black} ({g.black_rating ?? '?'})
        </h1>
        <span className="chip">you played {g.color} · <ResultPill result={g.result} /></span>
        <span className="chip">{g.time_class} · {g.opening ?? 'unknown opening'}</span>
        <span className={`chip ${g.status === 'done' ? 'cls-best' : g.status === 'failed' ? 'cls-blunder' : ''}`}>
          {g.status}{g.status === 'analyzing' ? ` ${g.progress ?? 0}%` : ''}
        </span>
        <div className="ml-auto flex gap-2">
          <button className="btn" onClick={() => setFlipped((f) => !f)}>Flip (f)</button>
          <button className="btn" onClick={() => navigator.clipboard.writeText(fen)}>Copy FEN</button>
          <button className="btn" onClick={downloadPgn}>Export PGN</button>
          <button className="btn" onClick={() => api.setFavorite(gameId, !g.favorite).then(load)}>
            {g.favorite ? '★ Favourite' : '☆ Favourite'}
          </button>
          <button className="btn btn-primary" onClick={runAnalysis}>
            {g.status === 'done' ? 'Re-analyze' : 'Analyze'}
          </button>
        </div>
      </div>

      {g.error && <ErrorNote>Analysis failed: {g.error}</ErrorNote>}
      {runId != null && g.status !== 'done' && <div className="card p-3 text-sm">Queued job #{runId}. Progress updates automatically.</div>}

      <div className="grid gap-4 lg:grid-cols-[minmax(320px,560px)_1fr]">
        <div className="space-y-3">
          <div className="flex gap-3">
            <EvalBar ev={evalToPercent(evalCp, evalMate)} height={520} />
            <div className="flex-1">
              <Board fen={fen} orientation={flipped ? 'black' : 'white'} arrows={arrows} squareStyles={squareStyles} />
              <div className="mt-2 flex items-center gap-2">
                <button className="btn" onClick={() => step(-1)}>◀</button>
                <button className="btn" onClick={() => step(1)}>▶</button>
                <button className="btn" onClick={() => setPly(0)}>⏮</button>
                <button className="btn" onClick={() => setPly(total)}>⏭</button>
                <span className="ml-2 text-sm">
                  Move {ply}/{total} · <EvalTag cp={evalCp} mate={evalMate} />
                </span>
                {material && (
                  <span className="ml-auto text-sm muted">
                    Material {material.diff === 0 ? 'equal' : material.diff > 0 ? `+${material.diff} white` : `${material.diff} black`}
                  </span>
                )}
              </div>
            </div>
          </div>

          <Card title="Evaluation graph">
            <EvalGraph moves={moves} selected={ply} onSelect={setPly} />
          </Card>

          <Card title="Engine lines" right={<span className="chip">{g.status === 'done' ? `depth from analysis` : 'not analysed'}</span>}>
            {current?.alternatives && current.alternatives.length > 0 ? (
              <ul className="space-y-1 font-mono text-sm">
                {current.alternatives.map((a: any) => (
                  <li key={a.rank} className="flex gap-2">
                    <span className="muted w-6">{a.rank}.</span>
                    <span className="w-16">{formatEval(a.cp ?? null, a.mate ?? null)}</span>
                    <span className="truncate">{a.uci}</span>
                    <span className="truncate muted">{a.pv?.slice(0, 6).join(' ')}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-sm muted">
                {current?.best_uci
                  ? <>Best move: <b>{current.best_uci}</b> · eval before: <EvalTag cp={current.best_eval_cp ?? null} mate={current.best_mate_in ?? null} /></>
                  : 'No alternatives stored (engine single-PV). Run an analysis.'}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-3">
          <Card title="Move list" right={<button className="btn" onClick={() => setPly(total)}>End</button>}>
            <MoveList moves={moves} selected={ply} onSelect={setPly} />
            <div className="mt-3"><ClassificationLegend /></div>
          </Card>

          {current && (
            <Card title={`Move ${current.move_number}${current.color === 'white' ? '.' : '...'} ${current.san}`}>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className={`chip cls-${current.classification}`}>
                  {CLASSIFICATION_LABEL[current.classification ?? ''] ?? current.classification}
                </span>
                {current.provisional && <span className="chip">provisional (shallow)</span>}
                {current.cp_loss != null && <span className="chip">loss {current.cp_loss}cp</span>}
                {current.best_uci && current.best_uci !== current.uci && (
                  <button className="chip" onClick={() => {
                    const b = uciSquares(current.best_uci!)
                    if (b) {
                      // jump to this move if it is the played move elsewhere; otherwise just highlight
                    }
                  }}>best: {current.best_uci}</button>
                )}
                {current.clock != null && <span className="chip">clock {fmtClock(current.clock)}</span>}
                {current.think != null && <span className="chip">thought {current.think.toFixed(1)}s</span>}
              </div>
              <p className="mt-2 text-sm">{current.explanation ?? 'No stored explanation.'}</p>
              {tacticsHere.length > 0 && (
                <div className="mt-2 text-sm">
                  <b>Tactics:</b>{' '}
                  {tacticsHere.map((t, i) => (
                    <span key={i} className="chip mr-1" title={JSON.stringify(t.detail)}>
                      {t.kind} {t.motif} ({Math.round(t.confidence * 100)}%)
                    </span>
                  ))}
                </div>
              )}
            </Card>
          )}

          <Card title="Game metadata">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div><span className="muted">Result</span><br />{g.white_result}–{g.black_result}</div>
              <div><span className="muted">Termination</span><br />{g.termination ?? '–'}</div>
              <div><span className="muted">ECO</span><br />{g.eco ?? '–'}</div>
              <div><span className="muted">Time control</span><br />{g.time_control ?? '–'}</div>
              <div><span className="muted">ACPL (you)</span><br />{g.acpl ?? '–'}</div>
              <div><span className="muted">Accuracy</span><br />{g.accuracy ?? '–'}</div>
              <div><span className="muted">Blunders / mistakes</span><br />{g.blunders ?? 0} / {g.mistakes ?? 0}</div>
              <div><span className="muted">Best-move rate</span><br />{g.best_move_rate ?? '–'}%</div>
            </div>
          </Card>

          <Card title="Your notes">
            <textarea
              className="input"
              rows={3}
              value={notes}
              onChange={(e) => { setNotes(e.target.value); setNoteSaved(false) }}
              placeholder="Add your own notes about this game…"
            />
            <div className="mt-2 flex items-center gap-2">
              <button className="btn" onClick={() => api.setNotes(gameId, notes).then(() => setNoteSaved(true))}>Save note</button>
              {noteSaved && <span className="text-sm cls-best">saved</span>}
              {ply >= 1 && (
                <button className="btn ml-auto" onClick={() => api.annotate(gameId, { ply, comment: notes || `note at move ${ply}`, tags: ['study'] }).then(() => load())}>
                  Save as annotation at move {ply}
                </button>
              )}
            </div>
            {detail.annotations.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs muted">
                {detail.annotations.map((a, i) => (
                  <li key={i}>ply {a.ply ?? '–'}: {a.comment}</li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}

function fmtClock(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
