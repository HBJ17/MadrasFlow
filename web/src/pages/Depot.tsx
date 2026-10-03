// Operator dashboard: fleet heatmap, advisories, scenario panel (twin what-if), data health, impact.
import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getJSON, hhmm, levelOf, postJSON, usePolling, type RouteInfo } from '../api'
import { LevelChip, SimBadge } from '../components'
import Heatmap from './depot/Heatmap'
import { CHART as C, Panel } from './depot/ui'

interface Advisory {
  advisory_id: number; route: string; route_id: string; direction: number; depot: string; slot_start: string; slot_end: string
  reason: string; action: string; extra_trips: number; expected_lf_before: number | null; expected_lf_after: number | null
  neighbour_lf_after: number | null; extra_vehicle_hours: number | null; status: string; created_at: string
}
interface Health {
  now: string; last_event_ts: string | null; sources: Record<string, number>; data_source: string; last_forecast_at: string | null
  forecast_rows: number; camera_nodes: { node_id: string; last_seen: string; fps: number | null; kind: string | null }[]
  camera_recent?: { ts: string; source: string; stop_id: string; vehicle_id: string | null; boardings: number; alightings: number; onboard_load: number | null; waiting_count: number | null }[]
}
interface Scenario { id: string; label: string; params: Record<string, unknown> }

function Advisories() {
  const a = usePolling<{ advisories: Advisory[]; data_source: 'twin' | 'camera' | 'mixed' }>('/advisories?status=active,accepted,rejected_by_whatif', 30_000)
  const [busy, setBusy] = useState(false)
  const act = async (id: number, action: 'accept' | 'dismiss') => { await postJSON(`/advisories/${id}/${action}`, {}); a.reload() }
  const runNow = async () => { setBusy(true); try { await postJSON('/advisories/run', {}) } finally { setBusy(false); a.reload() } }
  const list = a.data?.advisories ?? []
  return (
    <Panel title="Depot advisories" right={<button className="btn-ghost text-sm" disabled={busy} onClick={runNow}>{busy ? 'Testing in twin…' : 'Detect now'}</button>}>
      {!list.length ? <p className="text-sm text-slate-600 dark:text-slate-400">No overload predicted in the next 3 hours.</p> : null}
      <ul className="grid gap-3 md:grid-cols-2">
        {list.map((x) => (
          <li key={x.advisory_id} className={`rounded-xl p-3 ring-1 ${x.status === 'accepted' ? 'ring-teal-600' : x.status === 'rejected_by_whatif' ? 'ring-slate-300 opacity-70' : 'ring-amber-400'}`}>
            <div className="flex items-center justify-between gap-2">
              <b>{x.route} · dir {x.direction} · {x.depot} depot</b>
              <span className="text-xs uppercase">{x.status.replace(/_/g, ' ')}</span>
            </div>
            <p className="text-sm">{hhmm(x.slot_start)}–{hhmm(x.slot_end)} · {x.reason}</p>
            <p className="font-medium">➜ {x.action}</p>
            <p className="flex flex-wrap items-center gap-2 text-sm">
              Twin what-if: <LevelChip level={levelOf(x.expected_lf_before)} lf={x.expected_lf_before} size="md" /> → <LevelChip level={levelOf(x.expected_lf_after)} lf={x.expected_lf_after} size="md" />
              {x.neighbour_lf_after != null ? <span className="text-xs text-slate-600 dark:text-slate-400">neighbours ≤ {Math.round(x.neighbour_lf_after * 100)}%</span> : null}
              {x.extra_vehicle_hours != null ? <span className="text-xs text-slate-600 dark:text-slate-400">· +{x.extra_vehicle_hours} vehicle-h</span> : null}
            </p>
            {x.status === 'active' ? (
              <div className="mt-2 flex gap-2">
                <button className="btn-primary text-sm" onClick={() => act(x.advisory_id, 'accept')}>Accept</button>
                <button className="btn-ghost text-sm" onClick={() => act(x.advisory_id, 'dismiss')}>Dismiss</button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </Panel>
  )
}

interface RunResult {
  status: string; error?: string
  summary?: {
    hourly: { hour: number; lf_before: number; lf_after: number; left_behind_before: number; left_behind_after: number; crowded_before: number; crowded_after: number }[]
    scenario: Record<string, unknown>; baseline: Record<string, unknown>
    by_route: { route_id: string; baseline: number; scenario: number }[]
  }
}

function ScenarioPanel({ routes }: { routes: RouteInfo[] }) {
  const sc = usePolling<Scenario[]>('/twin/scenarios', 3600_000)
  const [id, setId] = useState('rain_heavy')
  const [xt, setXt] = useState({ route: 'BUS_95', direction: 0, start: '08:00', end: '10:00', n: 3 })
  const [custom, setCustom] = useState('{"demand_mult": {"bus": 1.2}, "run_time_mult": 1.1}')
  const [runId, setRunId] = useState<string | null>(null)
  const [res, setRes] = useState<RunResult | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!runId) return
    let alive = true
    const poll = async () => {
      try {
        const { data } = await getJSON<RunResult>(`/twin/run/${runId}`)
        if (!alive) return
        setRes(data)
        if (data.status === 'queued' || data.status === 'running') setTimeout(poll, 1500)
      } catch (e) { setErr(String(e)) }
    }
    poll()
    return () => { alive = false }
  }, [runId])

  const run = async () => {
    setErr(null); setRes({ status: 'queued' })
    let mods: Record<string, unknown> | null = null
    try {
      if (id === 'extra_trips') mods = { extra_trips: [xt] }
      if (id === 'custom') mods = JSON.parse(custom)
      const { data } = await postJSON<{ run_id: string }>('/twin/run', { scenario: id, days: 1, seed: 42, mods })
      setRunId(data.run_id)
    } catch (e) { setErr(String((e as Error).message)); setRes(null) }
  }
  const s = res?.summary
  const kpi = (k: string) => [Number((s?.baseline as Record<string, number>)?.[k] ?? 0), Number((s?.scenario as Record<string, number>)?.[k] ?? 0)]
  return (
    <Panel title="Scenario panel · run the digital twin" right={<SimBadge source="twin" />}>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="sc" className="mb-1 block text-sm font-medium">Scenario</label>
          <select id="sc" className="input w-64" value={id} onChange={(e) => setId(e.target.value)}>
            {sc.data?.filter((x) => x.id !== 'baseline').map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
          </select>
        </div>
        {id === 'extra_trips' ? (
          <>
            <div><label className="mb-1 block text-sm" htmlFor="xr">Route</label>
              <select id="xr" className="input w-28" value={xt.route} onChange={(e) => setXt({ ...xt, route: e.target.value })}>
                {routes.map((r) => <option key={r.route_id} value={r.route_id}>{r.short_name}</option>)}
              </select></div>
            <div><label className="mb-1 block text-sm" htmlFor="xd">Dir</label>
              <select id="xd" className="input w-20" value={xt.direction} onChange={(e) => setXt({ ...xt, direction: Number(e.target.value) })}><option value={0}>0</option><option value={1}>1</option></select></div>
            <div><label className="mb-1 block text-sm" htmlFor="xs">From</label><input id="xs" type="time" className="input w-32" value={xt.start} onChange={(e) => setXt({ ...xt, start: e.target.value })} /></div>
            <div><label className="mb-1 block text-sm" htmlFor="xe">To</label><input id="xe" type="time" className="input w-32" value={xt.end} onChange={(e) => setXt({ ...xt, end: e.target.value })} /></div>
            <div><label className="mb-1 block text-sm" htmlFor="xn">Trips</label><input id="xn" type="number" min={1} max={20} className="input w-20" value={xt.n} onChange={(e) => setXt({ ...xt, n: Number(e.target.value) })} /></div>
          </>
        ) : null}
        {id === 'custom' ? (
          <div className="flex-1"><label className="mb-1 block text-sm" htmlFor="cj">Multipliers (JSON)</label>
            <input id="cj" className="input font-mono text-sm" value={custom} onChange={(e) => setCustom(e.target.value)} /></div>
        ) : null}
        <button className="btn-primary" onClick={run} disabled={res?.status === 'queued' || res?.status === 'running'}>▶ Run twin</button>
      </div>
      <p className="text-xs text-slate-600 dark:text-slate-400">{sc.data?.find((x) => x.id === id) ? JSON.stringify(sc.data.find((x) => x.id === id)!.params) : ''}</p>
      {err ? <p role="alert" className="text-sm text-red-700">{err}</p> : null}
      {res && (res.status === 'queued' || res.status === 'running') ? (
        <div role="status" className="flex items-center gap-3 text-sm"><span className="h-2 w-40 animate-pulse rounded bg-teal-600/60" /> Simulating baseline and scenario day (≈ 20–40 s)…</div>
      ) : null}
      {res?.status === 'error' ? <p className="text-sm text-red-700">Twin run failed: {res.error}</p> : null}
      {s ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-4">
            {[['Boardings', 'boardings_total'], ['CROWDED vehicle-stops', 'crowded_vehicle_stops'], ['Left behind', 'left_behind_total'], ['Gave up (unmet)', 'unmet_demand']].map(([l, k]) => {
              const [b, a] = kpi(k)
              return (
                <div key={k} className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800">
                  <div className="text-xs text-slate-600 dark:text-slate-400">{l}</div>
                  <div className="text-xl font-bold tabular-nums">{a.toLocaleString('en-IN')}</div>
                  <div className="text-xs tabular-nums text-slate-600 dark:text-slate-400">baseline {b.toLocaleString('en-IN')} ({b ? `${a >= b ? '+' : ''}${Math.round((a / b - 1) * 100)}%` : '–'})</div>
                </div>
              )
            })}
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <ChartBox title="Load factor (P90) by hour">
              <LineChart data={s.hourly}><CartesianGrid strokeDasharray="3 3" stroke={C.grid} /><XAxis dataKey="hour" /><YAxis domain={[0, 'auto']} />
                <Tooltip /><Legend /><ReferenceLine y={1} stroke="#b91c1c" strokeDasharray="4 4" />
                <Line dataKey="lf_before" name="baseline" stroke={C.before} dot={false} strokeWidth={2.5} strokeDasharray="5 3" isAnimationActive={false} />
                <Line dataKey="lf_after" name="scenario" stroke={C.after} dot={false} strokeWidth={2.5} isAnimationActive={false} /></LineChart>
            </ChartBox>
            <ChartBox title="Passengers left behind by hour">
              <BarChart data={s.hourly}><CartesianGrid strokeDasharray="3 3" stroke={C.grid} /><XAxis dataKey="hour" /><YAxis /><Tooltip /><Legend />
                <Bar dataKey="left_behind_before" name="baseline" fill={C.before} isAnimationActive={false} /><Bar dataKey="left_behind_after" name="scenario" fill={C.after} isAnimationActive={false} /></BarChart>
            </ChartBox>
            <ChartBox title="CROWDED vehicle-stops by hour">
              <BarChart data={s.hourly}><CartesianGrid strokeDasharray="3 3" stroke={C.grid} /><XAxis dataKey="hour" /><YAxis /><Tooltip /><Legend />
                <Bar dataKey="crowded_before" name="baseline" fill={C.before} isAnimationActive={false} /><Bar dataKey="crowded_after" name="scenario" fill={C.after} isAnimationActive={false} /></BarChart>
            </ChartBox>
          </div>
          <table className="text-sm">
            <thead><tr className="text-left text-slate-600 dark:text-slate-400"><th className="pr-6">Route</th><th className="pr-6 text-right">Baseline boardings</th><th className="text-right">Scenario</th></tr></thead>
            <tbody>{s.by_route.map((r) => <tr key={r.route_id}><td className="pr-6">{routes.find((x) => x.route_id === r.route_id)?.short_name ?? r.route_id}</td><td className="pr-6 text-right tabular-nums">{r.baseline.toLocaleString('en-IN')}</td><td className="text-right tabular-nums">{r.scenario.toLocaleString('en-IN')}</td></tr>)}</tbody>
          </table>
        </div>
      ) : null}
    </Panel>
  )
}

function ChartBox({ title, children }: { title: string; children: React.ReactElement }) {
  return (
    <figure className="space-y-1">
      <figcaption className="text-sm font-medium">{title}</figcaption>
      <div className="h-56"><ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer></div>
    </figure>
  )
}

function DataHealth() {
  const h = usePolling<Health>('/health', 2000)
  const acc = usePolling<{ models: Record<string, { n: number; mae_lf: number; level_acc: number }>; note?: string }>('/accuracy', 120_000)
  const d = h.data
  return (
    <Panel title="Data health" right={<SimBadge source={d?.data_source as 'twin'} />}>
      {d ? (
        <div className="grid gap-4 text-sm md:grid-cols-3">
          <div>
            <h3 className="font-medium">Events by source</h3>
            <ul>{Object.entries(d.sources).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}{k === 'twin' ? ' (simulated)' : ''}</span><span className="tabular-nums">{v.toLocaleString('en-IN')}</span></li>)}</ul>
            <p className="mt-1 text-slate-600 dark:text-slate-400">Last event {d.last_event_ts ? hhmm(d.last_event_ts) : '–'} · forecast {d.last_forecast_at ? hhmm(d.last_forecast_at) : '–'}</p>
          </div>
          <div>
            <h3 className="font-medium">Camera nodes</h3>
            {d.camera_nodes.length ? d.camera_nodes.map((n) => {
              const age = (Date.now() - new Date(n.last_seen).getTime()) / 1000
              return <div key={n.node_id} className="flex justify-between"><span>{age < 120 ? '🟢' : '⚪'} {n.node_id} <span className="text-slate-600 dark:text-slate-400">{n.kind}</span></span><span>{n.fps ? `${n.fps.toFixed(1)} fps` : ''} · {Math.round(age)} s ago</span></div>
            }) : <p className="text-slate-600 dark:text-slate-400">No camera node has reported yet.</p>}
            <ul className="mt-2 space-y-0.5">
              {(d.camera_recent ?? []).slice(0, 6).map((c, i) => (
                <li key={i} className="tabular-nums">{hhmm(c.ts)} {c.source === 'camera_stop' ? `stop ${c.stop_id}: ${c.waiting_count} waiting` : `${c.vehicle_id} @ ${c.stop_id}: +${c.boardings} −${c.alightings} → ${c.onboard_load} on board`}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="font-medium">Forecast accuracy · last 24 h (1 h ahead)</h3>
            {acc.data && Object.keys(acc.data.models).length ? (
              <ul>{Object.entries(acc.data.models).map(([m, v]) => <li key={m} className="flex justify-between"><span>{m}</span><span className="tabular-nums">MAE {v.mae_lf.toFixed(3)} · level {Math.round(v.level_acc * 100)}% · n {v.n}</span></li>)}</ul>
            ) : <p className="text-slate-600 dark:text-slate-400">{acc.data?.note ?? 'Accumulating…'}</p>}
          </div>
        </div>
      ) : null}
    </Panel>
  )
}

function Impact() {
  const i = usePolling<Record<string, { before: number; after: number; change: string } | number | string>>('/impact', 3600_000)
  if (!i.data) return null
  const row = (k: string, l: string) => {
    const v = i.data![k] as { before: number; after: number; change: string }
    return <tr key={k}><td className="pr-6">{l}</td><td className="pr-6 text-right tabular-nums">{v.before.toLocaleString('en-IN')}</td><td className="pr-6 text-right tabular-nums">{v.after.toLocaleString('en-IN')}</td><td className="text-right font-semibold">{v.change}</td></tr>
  }
  return (
    <Panel title="Impact if advisories are followed (computed by the twin)" right={<SimBadge source="twin" />}>
      <table className="text-sm">
        <thead><tr className="text-left text-slate-600 dark:text-slate-400"><th className="pr-6">Per simulated weekday (MTC routes)</th><th className="pr-6 text-right">Baseline</th><th className="pr-6 text-right">Advised</th><th className="text-right">Change</th></tr></thead>
        <tbody>
          {row('crowded_vehicle_stops_per_day', 'CROWDED vehicle-stops')}
          {row('left_behind_per_day', 'Passengers left behind')}
          {row('peak_lf_p90', 'Busiest-slot load factor (95th pct)')}
        </tbody>
      </table>
      <p className="text-sm">Cost: +{String(i.data.extra_trips_per_day)} trips, +{String(i.data.extra_bus_hours_per_day)} bus-hours per day.</p>
    </Panel>
  )
}

export default function Depot() {
  const routes = usePolling<RouteInfo[]>('/routes', 3600_000)
  const r = routes.data ?? []
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Depot dashboard</h1>
      <Heatmap />
      <Advisories />
      <ScenarioPanel routes={r} />
      <div className="grid gap-4 xl:grid-cols-2"><DataHealth /><Impact /></div>
    </div>
  )
}
