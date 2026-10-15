import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Card, ErrorNote, Stat } from '../components/ui'

export default function Onboarding() {
  const [username, setUsername] = useState('')
  const [preview, setPreview] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [logs, setLogs] = useState<any[]>([])
  const [pgn, setPgn] = useState('')
  const [pgnMsg, setPgnMsg] = useState<string | null>(null)
  const [allHistory, setAllHistory] = useState(false)
  const [months, setMonths] = useState(3)
  const [tcs, setTcs] = useState<string[]>([])

  const loadMe = () => api.me().then((r) => { if (r.account) setUsername(r.account.username) })
  useEffect(() => { loadMe() }, [])

  const poll = () => {
    api.importLogs().then((r) => setLogs(r.logs)).catch(() => {})
  }
  useEffect(() => {
    poll()
    const t = setInterval(poll, 3000)
    return () => clearInterval(t)
  }, [])

  const doPreview = async () => {
    setBusy(true); setErr(null)
    try { setPreview(await api.preview(username)) }
    catch (e) { setErr(String(e)) }
    finally { setBusy(false) }
  }

  const doConnect = async () => {
    setBusy(true); setErr(null)
    try { await api.onboard(username); setPreview(await api.preview(username)) }
    catch (e) { setErr(String(e)) }
    finally { setBusy(false) }
  }

  const doImport = async () => {
    setBusy(true); setErr(null)
    try {
      await api.importChesscom({ months: allHistory ? null : months, all_history: allHistory, time_classes: tcs.length ? tcs : null })
      poll()
    } catch (e) { setErr(String(e)) }
    finally { setBusy(false) }
  }

  const doPgn = async () => {
    setBusy(true); setPgnMsg(null); setErr(null)
    try {
      const r = await api.importPgn(pgn, username || undefined)
      setPgnMsg(`Imported ${r.imported} game(s), skipped ${r.skipped}.`)
      setPgn('')
    } catch (e) { setErr(String(e)) }
    finally { setBusy(false) }
  }

  const stats = preview?.stats ?? {}
  const tcKeys = Object.keys(stats).filter((k) => k.startsWith('chess_'))

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Connect your games</h1>
      {err && <ErrorNote>{err}</ErrorNote>}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Chess.com account">
          <p className="mb-3 text-sm muted">
            We read only public data through the documented Chess.com public API. No password is ever requested or stored.
          </p>
          <div className="flex gap-2">
            <input className="input" placeholder="chess.com username" value={username}
                   onChange={(e) => setUsername(e.target.value)}
                   onKeyDown={(e) => e.key === 'Enter' && doPreview()} />
            <button className="btn" disabled={busy || !username} onClick={doPreview}>Look up</button>
            <button className="btn btn-primary" disabled={busy || !username} onClick={doConnect}>Connect</button>
          </div>

          {preview && (
            <div className="mt-4 space-y-3">
              <div className="flex items-center gap-3">
                {preview.avatar && <img src={preview.avatar} alt="" className="h-12 w-12 rounded-lg" />}
                <div>
                  <div className="font-semibold">
                    {preview.title ? `${preview.title} ` : ''}{preview.username}
                  </div>
                  <div className="text-xs muted">{preview.name ?? ''} · {preview.status}</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {tcKeys.map((k) => (
                  <Stat key={k} label={k.replace('chess_', '')} value={stats[k]?.last?.rating ?? '–'}
                        sub={`best ${stats[k]?.best?.rating ?? '–'}`} />
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card title="Import options">
          <div className="space-y-3 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={allHistory} onChange={(e) => setAllHistory(e.target.checked)} />
              Import all accessible history
            </label>
            {!allHistory && (
              <label className="flex items-center gap-2">
                Recent months
                <input type="number" className="input w-24" min={1} max={60} value={months}
                       onChange={(e) => setMonths(Number(e.target.value))} />
              </label>
            )}
            <div>
              <div className="mb-1 muted">Time controls</div>
              {['bullet', 'blitz', 'rapid', 'daily'].map((t) => (
                <label key={t} className="mr-3 inline-flex items-center gap-1">
                  <input type="checkbox" checked={tcs.includes(t)}
                         onChange={(e) => setTcs((v) => e.target.checked ? [...v, t] : v.filter((x) => x !== t))} />
                  {t}
                </label>
              ))}
            </div>
            <button className="btn btn-primary" disabled={busy} onClick={doImport}>Start import</button>
            <p className="text-xs muted">
              Imports run in the background and respect Chess.com rate limits. Re-running is safe: duplicate games are skipped.
            </p>
          </div>
        </Card>

        <Card title="Import progress">
          {logs.length === 0 ? <div className="muted text-sm">No imports yet.</div> : (
            <table className="data">
              <thead><tr><th>When</th><th>Kind</th><th>Status</th><th>Imported</th><th>Skipped</th></tr></thead>
              <tbody>
                {logs.map((l) => (
                  <tr key={l.id}>
                    <td>{l.created_at ? new Date(l.created_at).toLocaleTimeString() : '–'}</td>
                    <td>{l.kind}</td>
                    <td><span className="chip">{l.status}</span></td>
                    <td>{l.imported}</td><td>{l.skipped}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {logs.some((l) => l.error) && <div className="mt-2 text-xs" style={{ color: '#f87171' }}>{logs.find((l) => l.error)?.error}</div>}
        </Card>

        <Card title="Manual PGN import">
          <p className="mb-2 text-sm muted">Paste one or more PGN games (multi-game files supported). Works even without a connected account.</p>
          <textarea className="input font-mono text-xs" rows={7} value={pgn} onChange={(e) => setPgn(e.target.value)}
                    placeholder="[Event ...]&#10;&#10;1. e4 e5 2. Nf3 ..." />
          <div className="mt-2 flex items-center gap-2">
            <button className="btn btn-primary" disabled={busy || !pgn.trim()} onClick={doPgn}>Import PGN</button>
            {pgnMsg && <span className="text-sm cls-best">{pgnMsg}</span>}
          </div>
          <Link to="/games" className="btn mt-3 inline-block">Go to My Games</Link>
        </Card>
      </div>
    </div>
  )
}
