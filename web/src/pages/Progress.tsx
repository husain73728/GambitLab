import { useEffect, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Card, Empty, ErrorNote, Loading, Stat } from '../components/ui'

export default function Progress() {
  const [window_, setWindow] = useState(50)
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { setData(null); api.progress(window_).then(setData).catch((e) => setErr(String(e))) }, [window_])

  if (err) return <ErrorNote>{err}</ErrorNote>
  if (!data) return <Loading />
  if (!data.has_data) return <Empty title="Not enough analysed games" hint="Analyse some games to see progress over time." />

  const series = data.series.map((s: any, i: number) => ({ i, ...s }))

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-bold">Progress</h1>
        <select className="input w-40 ml-auto" value={window_} onChange={(e) => setWindow(Number(e.target.value))}>
          {[20, 50, 100, 200].map((w) => <option key={w} value={w}>last {w} games</option>)}
        </select>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={`Recent ACPL (${data.window})`} value={data.recent.avg_acpl ?? '–'} tone="warn"
              sub={`previous: ${data.previous.avg_acpl ?? '–'}`} />
        <Stat label="Recent blunders / game" value={data.recent.blunders_pg ?? '–'}
              sub={`previous: ${data.previous.blunders_pg ?? '–'}`} />
        <Stat label="Recent win rate" value={`${data.recent.win_rate ?? 0}%`}
              sub={`previous: ${data.previous.win_rate ?? 0}%`} />
        <Stat label="Games compared" value={`${data.recent.games} vs ${data.previous.games}`} />
      </div>

      <Card title="Average centipawn loss over time">
        <div style={{ height: 220 }}>
          <ResponsiveContainer>
            <LineChart data={series}>
              <CartesianGrid stroke="#1f2841" strokeDasharray="3 3" />
              <XAxis dataKey="i" tick={false} height={4} />
              <YAxis tick={{ fill: '#93a0c4', fontSize: 10 }} />
              <Tooltip contentStyle={{ background: '#131a2c', border: '1px solid #27304f', borderRadius: 8 }} />
              <Line type="monotone" dataKey="acpl" stroke="#fbbf24" dot={false} name="ACPL" isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Blunders per game">
          <div style={{ height: 200 }}>
            <ResponsiveContainer>
              <LineChart data={series}>
                <CartesianGrid stroke="#1f2841" strokeDasharray="3 3" />
                <XAxis dataKey="i" tick={false} height={4} />
                <YAxis tick={{ fill: '#93a0c4', fontSize: 10 }} allowDecimals={false} />
                <Tooltip contentStyle={{ background: '#131a2c', border: '1px solid #27304f', borderRadius: 8 }} />
                <Line type="monotone" dataKey="blunders" stroke="#f87171" dot={false} name="Blunders" isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Rating">
          <div style={{ height: 200 }}>
            <ResponsiveContainer>
              <LineChart data={series}>
                <CartesianGrid stroke="#1f2841" strokeDasharray="3 3" />
                <XAxis dataKey="i" tick={false} height={4} />
                <YAxis tick={{ fill: '#93a0c4', fontSize: 10 }} domain={['auto', 'auto']} />
                <Tooltip contentStyle={{ background: '#131a2c', border: '1px solid #27304f', borderRadius: 8 }} />
                <Line type="monotone" dataKey="rating" stroke="#34d399" dot={false} name="Rating" isAnimationActive={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="card p-3 text-xs muted">{data.disclaimer}</div>
    </div>
  )
}
