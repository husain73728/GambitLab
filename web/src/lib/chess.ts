import { Chess } from 'chess.js'

export function piecesFromFen(fen: string) {
  const chess = new Chess()
  chess.load(fen)
  return chess.board()
}

export function turnFromFen(fen: string): 'w' | 'b' {
  try {
    const chess = new Chess(fen)
    return chess.turn()
  } catch {
    return 'w'
  }
}

export function uciSquares(uci: string): { from: string; to: string } | null {
  if (!uci || uci.length < 4) return null
  return { from: uci.slice(0, 2), to: uci.slice(2, 4) }
}

const VALUES: Record<string, number> = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 }

export function materialFromFen(fen: string) {
  const rows = fen.split(' ')[0].split('/')
  let white = 0
  let black = 0
  for (const row of rows) {
    for (const ch of row) {
      const lower = ch.toLowerCase()
      if (!(lower in VALUES)) continue
      if (ch === ch.toUpperCase()) white += VALUES[lower]
      else black += VALUES[lower]
    }
  }
  return { white, black, diff: white - black }
}

/** Convert a signed centipawn / mate score (white POV) to a 0..100 white advantage bar. */
export function evalToPercent(cp: number | null, mate: number | null): number {
  if (mate != null) return mate > 0 ? 100 : 0
  if (cp == null) return 50
  const clamped = Math.max(-1000, Math.min(1000, cp))
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * clamped)) - 1)
}

export function formatEval(cp: number | null, mate: number | null): string {
  if (mate != null) return `#${mate > 0 ? '' : '-'}${Math.abs(mate)}`
  if (cp == null) return '–'
  const v = cp / 100
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}`
}

/** Numeric value for charts (mate mapped to a large value). */
export function evalToNumber(cp: number | null, mate: number | null): number {
  if (mate != null) return mate > 0 ? 10 : -10
  return (cp ?? 0) / 100
}

export const CLASSIFICATION_LABEL: Record<string, string> = {
  best: 'Best',
  excellent: 'Excellent',
  good: 'Good',
  book: 'Book',
  inaccuracy: 'Inaccuracy',
  mistake: 'Mistake',
  blunder: 'Blunder',
  missed_win: 'Missed win',
  missed_mate: 'Missed mate',
  forced: 'Forced',
}

export const CLASSIFICATION_GLYPH: Record<string, string> = {
  best: '★',
  excellent: '✓',
  good: '',
  book: '📖',
  inaccuracy: '?!',
  mistake: '?',
  blunder: '??',
  missed_win: '✗',
  missed_mate: '✗',
  forced: '→',
}

export function sanList(_fens: string[], _startFen: string): string[] {
  return []
}
