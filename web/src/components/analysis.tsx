import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Move } from '../api'
import { CLASSIFICATION_GLYPH, CLASSIFICATION_LABEL, evalToNumber, formatEval } from '../lib/chess'

export function EvalBar({ ev, height = 360 }: { ev: number; height?: number }) {
  // ev is 0..100 (white share). Rendered top = black, bottom = white.
  const white = Math.max(2, Math.min(98, ev))
  return (
    <div
      className="relative w-6 overflow-hidden rounded"
      style={{ height, background: '#0f1526', border: '1px solid var(--line)' }}
      title={`White ${white.toFixed(0)}%`}
    >
      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: `${white}%`, background: 'linear-gradient(180deg,#e5ecff,#ffffff)' }} />
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: `${100 - white}%`, background: 'linear-gradient(180deg,#0b1020,#1b2340)' }} />
    </div>
  )
}

export function EvalGraph({ moves, selected, onSelect }: {
  moves: Move[]; selected: number; onSelect: (ply: number) => void
}) {
  const data = moves.map((m) => ({
    ply: m.ply,
    label: `${Math.ceil(m.ply / 2)}${m.color === 'white' ? '.' : '...'}${m.san}`,
    eval: evalToNumber(m.eval_cp ?? null, m.eval_mate_in ?? null),
    classification: m.classification,
  }))
  return (
    <div style={{ width: '100%', height: 150 }}>
      <ResponsiveContainer>
        <AreaChart
          data={data}
          margin={{ top: 6, right: 8, left: -22, bottom: 0 }}
          onClick={(e: any) => {
            if (e && e.activePayload && e.activePayload[0]) onSelect(e.activePayload[0].payload.ply)
          }}
        >
          <defs>
            <linearGradient id="evalFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#60a5fa" stopOpacity={0.75} />
              <stop offset="100%" stopColor="#0b1020" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1f2841" strokeDasharray="3 3" />
          <XAxis dataKey="ply" tick={false} height={4} />
          <YAxis domain={[-6, 6]} tick={{ fill: '#93a0c4', fontSize: 10 }} />
          <ReferenceLine y={0} stroke="#3b4d6b" />
          <Tooltip
            contentStyle={{ background: '#131a2c', border: '1px solid #27304f', borderRadius: 8, fontSize: 12 }}
            formatter={(v: any, _n: any, p: any) => [`${(v as number).toFixed(2)}`, p?.payload?.label]}
          />
          <Area type="monotone" dataKey="eval" stroke="#60a5fa" strokeWidth={2} fill="url(#evalFill)" isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
      <div className="mt-1 text-[11px] muted">Click the graph to jump to a move. Positive = white better.</div>
      <div className="sr-only">{selected}</div>
    </div>
  )
}

export function MoveList({ moves, selected, onSelect }: {
  moves: Move[]; selected: number; onSelect: (ply: number) => void
}) {
  const rows: { n: number; white?: Move; black?: Move }[] = []
  for (const m of moves) {
    const n = m.move_number
    let row = rows.find((r) => r.n === n)
    if (!row) { row = { n }; rows.push(row) }
    if (m.color === 'white') row.white = m
    else row.black = m
  }
  const Cell = ({ m }: { m?: Move }) => {
    if (!m) return <span className="muted">–</span>
    const cls = m.classification ?? ''
    return (
      <button
        className={`move-btn cls-${cls} ${selected === m.ply ? 'active' : ''}`}
        onClick={() => onSelect(m.ply)}
        title={m.explanation ?? ''}
      >
        {m.san}
        {CLASSIFICATION_GLYPH[cls] ? <span className="ml-1 text-[11px]">{CLASSIFICATION_GLYPH[cls]}</span> : null}
      </button>
    )
  }
  return (
    <div className="scroll" style={{ maxHeight: 420 }}>
      <div className="move-row text-[11px] uppercase muted" style={{ borderBottom: '1px solid var(--line)' }}>
        <div className="px-1 py-1">#</div><div>White</div><div>Black</div>
      </div>
      {rows.map((r) => (
        <div key={r.n} className="move-row" style={{ borderBottom: '1px solid #1b2138' }}>
          <div className="px-1 py-0.5 text-xs muted">{r.n}</div>
          <Cell m={r.white} />
          <Cell m={r.black} />
        </div>
      ))}
    </div>
  )
}

export function ClassificationLegend() {
  const keys = ['best', 'excellent', 'good', 'book', 'inaccuracy', 'mistake', 'blunder', 'missed_win', 'missed_mate']
  return (
    <div className="flex flex-wrap gap-2 text-[11px]">
      {keys.map((k) => (
        <span key={k} className={`chip cls-${k}`}>{CLASSIFICATION_LABEL[k]}</span>
      ))}
    </div>
  )
}

export function EvalTag({ cp, mate }: { cp?: number | null; mate?: number | null }) {
  const txt = formatEval(cp ?? null, mate ?? null)
  const white = (cp ?? 0) >= 0
  return <span className="font-mono" style={{ color: mate != null ? '#f472b6' : white ? '#e6ebff' : '#cbd5e1' }}>{txt}</span>
}
