import type { ReactNode } from 'react'

export function Card({ title, right, children, className = '' }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={`card p-4 ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="font-semibold">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

export function Stat({ label, value, sub, tone }: {
  label: string; value: ReactNode; sub?: ReactNode; tone?: 'good' | 'bad' | 'warn'
}) {
  const color = tone === 'good' ? '#86efac' : tone === 'bad' ? '#f87171' : tone === 'warn' ? '#fbbf24' : undefined
  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wide muted">{label}</div>
      <div className="mt-1 text-2xl font-bold" style={{ color }}>{value}</div>
      {sub && <div className="mt-1 text-xs muted">{sub}</div>}
    </div>
  )
}

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const map: Record<string, string> = {
    win: '#14532d', loss: '#7f1d1d', draw: '#1f2937',
    blunder: '#7f1d1d', mistake: '#78350f', inaccuracy: '#713f12',
    best: '#14532d', excellent: '#14532d', good: '#1e293b', book: '#1e293b',
    missed_win: '#831843', missed_mate: '#831843', forced: '#1e293b',
  }
  return (
    <span className="chip" style={{ background: tone ? map[tone] ?? '#0f1526' : '#0f1526' }}>
      {children}
    </span>
  )
}

export function Empty({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="card p-8 text-center">
      <div className="text-lg font-semibold">{title}</div>
      {hint && <div className="mt-2 text-sm muted">{hint}</div>}
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="p-8 text-center muted">{label}</div>
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div className="card p-3 text-sm" style={{ borderColor: '#7f1d1d', background: '#2a1215' }}>
      {children}
    </div>
  )
}

export function ResultPill({ result }: { result?: string | null }) {
  if (!result) return <span className="muted">–</span>
  const tone = result === 'win' ? '#86efac' : result === 'loss' ? '#f87171' : '#cbd5e1'
  const letter = result === 'win' ? 'W' : result === 'loss' ? 'L' : 'D'
  return <span className="font-bold" style={{ color: tone }}>{letter}</span>
}
