import { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Empty, ErrorNote, Loading, Stat } from '../components/ui'

export default function ClockPage() {
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.clock().then(setData).catch((e) => setErr(String(e))) }, [])
  if (err) return <ErrorNote>{err}</ErrorNote>
  if (!data) return <Loading />

  if (!data.has_data) {
    return <Empty title="No clock data" hint={data.note ?? 'Import games that include %clk clock stamps (most Chess.com games do).'} />
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Clock & time management</h1>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Games with clock data" value={data.games_with_clock} />
        <Stat label="Average think time" value={data.avg_think_seconds != null ? `${data.avg_think_seconds}s` : '–'} />
        <Stat label="Errors under pressure" value={data.errors_under_pressure} tone="bad"
              sub={`≤ ${data.time_pressure_threshold}s remaining`} />
        <Stat label="Time forfeits" value={data.time_forfeits} tone="warn" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Average thinking time by phase">
          <table className="data">
            <thead><tr><th>Phase</th><th>Avg seconds</th></tr></thead>
            <tbody>
              {Object.entries(data.by_phase).map(([k, v]: any) => (
                <tr key={k} style={{ cursor: 'default' }}><td className="capitalize">{k}</td><td>{v}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Increment usage">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Games with increment" value={data.games_with_increment} />
            <Stat label="Games without increment" value={data.games_without_increment} />
          </div>
          <p className="mt-3 text-xs muted">
            Thinking time is derived from PGN clock stamps (previous remaining − current remaining + increment).
            Games without clock data are excluded. {data.note}
          </p>
        </Card>
      </div>
    </div>
  )
}
