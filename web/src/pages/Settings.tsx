import { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, ErrorNote, Loading } from '../components/ui'

export default function Settings() {
  const [data, setData] = useState<any>(null)
  const [probe, setProbe] = useState<any>(null)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const load = () => api.engineSettings().then(setData).catch((e) => setErr(String(e)))
  useEffect(() => { load() }, [])

  if (err) return <ErrorNote>{err}</ErrorNote>
  if (!data) return <Loading />

  const p = data.primary
  const set = (k: string, v: any) => setData({ ...data, primary: { ...p, [k]: v } })

  const save = async () => {
    await api.updateEngine({
      path: p.path, threads: p.threads, hash_mb: p.hash_mb, depth: p.depth,
      timeout_s: p.timeout_s, multipv: p.multipv, name: p.name,
    })
    setSaved(true); setTimeout(() => setSaved(false), 2000); load()
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Settings</h1>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Primary engine (UCI)">
          <div className="space-y-3 text-sm">
            <label className="block">
              <span className="muted">Executable path</span>
              <input className="input mt-1 font-mono text-xs" value={p.path} onChange={(e) => set('path', e.target.value)} />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label><span className="muted">Name</span><input className="input mt-1" value={p.name} onChange={(e) => set('name', e.target.value)} /></label>
              <label><span className="muted">Threads</span><input type="number" className="input mt-1" value={p.threads} onChange={(e) => set('threads', Number(e.target.value))} /></label>
              <label><span className="muted">Hash (MB)</span><input type="number" className="input mt-1" value={p.hash_mb} onChange={(e) => set('hash_mb', Number(e.target.value))} /></label>
              <label><span className="muted">Depth</span><input type="number" className="input mt-1" value={p.depth} onChange={(e) => set('depth', Number(e.target.value))} /></label>
              <label><span className="muted">MultiPV</span><input type="number" className="input mt-1" value={p.multipv} onChange={(e) => set('multipv', Number(e.target.value))} /></label>
              <label><span className="muted">Timeout (s)</span><input type="number" className="input mt-1" value={p.timeout_s} onChange={(e) => set('timeout_s', Number(e.target.value))} /></label>
            </div>
            <div className="flex items-center gap-2">
              <button className="btn btn-primary" onClick={save}>Save</button>
              <button className="btn" onClick={() => api.probeEngine().then((r) => { setProbe(r.probe); load() })}>Probe availability</button>
              {saved && <span className="cls-best">saved</span>}
            </div>
            <div className="text-xs muted">
              Status:{' '}
              {p.available === true ? <span className="cls-best">available</span>
                : p.available === false ? <span className="cls-blunder">not available</span>
                : 'unknown (probe it)'}
              {p.version && <> · <span className="font-mono">{p.version}</span></>}
            </div>
            {probe && (
              <pre className="overflow-auto text-xs muted">{JSON.stringify(probe, null, 2)}</pre>
            )}
          </div>
        </Card>

        <Card title="Installation notes">
          <div className="space-y-2 text-sm">
            <p>
              GambitLab ships using the bundled <b>xdsa</b> engine at <code>engine/build/engine.exe</code>.
              It speaks UCI and is used as the default analyser.
            </p>
            <p className="muted">
              For stronger, faster analysis you can point the path at <b>Stockfish</b> instead. Download a
              UCI build for Windows, then set the path above and press “Probe availability”.
            </p>
            <ul className="list-disc pl-5 muted">
              <li>Engine analysis is stored with full provenance: engine name, version, depth, MultiPV, settings.</li>
              <li>Analyses are cached per position, so re-running a game is instant.</li>
              <li>Two engines agreeing is treated as supporting evidence, never as proof of correctness.</li>
            </ul>
            <p className="text-xs muted">
              Current defaults: fast depth {data.defaults.fast_depth}, deep depth {data.defaults.deep_depth}.
            </p>
          </div>
        </Card>
      </div>
    </div>
  )
}
