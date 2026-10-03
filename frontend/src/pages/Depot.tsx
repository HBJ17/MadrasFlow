// Operator dashboard: fleet heatmap, recommendations, what-if simulator (digital twin), data health, impact.
import { hhmm, usePolling, type RouteInfo } from '../api'
import { SimBadge } from '../components'
import Advisories from './depot/Advisories'
import Heatmap from './depot/Heatmap'
import ScenarioBuilder from './depot/ScenarioBuilder'
import { Panel } from './depot/ui'

interface Health {
  now: string; last_event_ts: string | null; sources: Record<string, number>; data_source: string; last_forecast_at: string | null
  forecast_rows: number; camera_nodes: { node_id: string; last_seen: string; fps: number | null; kind: string | null }[]
  camera_recent?: { ts: string; source: string; stop_id: string; vehicle_id: string | null; boardings: number; alightings: number; onboard_load: number | null; waiting_count: number | null }[]
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
            <h3 className="ledger mb-1.5">Events by source</h3>
            <ul>{Object.entries(d.sources).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}{k === 'twin' ? ' (simulated)' : ''}</span><span className="font-mono tabular-nums">{v.toLocaleString('en-IN')}</span></li>)}</ul>
            <p className="mt-1 text-slate-600 dark:text-slate-400">Last event {d.last_event_ts ? hhmm(d.last_event_ts) : '–'} · forecast {d.last_forecast_at ? hhmm(d.last_forecast_at) : '–'}</p>
          </div>
          <div>
            <h3 className="ledger mb-1.5">Camera nodes</h3>
            {d.camera_nodes.length ? d.camera_nodes.map((n) => {
              const age = (Date.now() - new Date(n.last_seen).getTime()) / 1000
              return <div key={n.node_id} className="flex justify-between"><span>{age < 120 ? '🟢' : '⚪'} {n.node_id} <span className="text-slate-600 dark:text-slate-400">{n.kind}</span></span><span>{n.fps ? `${n.fps.toFixed(1)} fps` : ''} · {Math.round(age)} s ago</span></div>
            }) : <p className="text-slate-600 dark:text-slate-400">No camera node has reported yet.</p>}
            <ul className="mt-2 space-y-0.5">
              {(d.camera_recent ?? []).slice(0, 6).map((c, i) => (
                <li key={i} className="font-mono text-xs tabular-nums">{hhmm(c.ts)} {c.source === 'camera_stop' ? `stop ${c.stop_id}: ${c.waiting_count} waiting` : `${c.vehicle_id} @ ${c.stop_id}: +${c.boardings} −${c.alightings} → ${c.onboard_load} on board`}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="ledger mb-1.5">Forecast accuracy · last 24 h (1 h ahead)</h3>
            {acc.data && Object.keys(acc.data.models).length ? (
              <ul>{Object.entries(acc.data.models).map(([m, v]) => <li key={m} className="flex justify-between"><span>{m}</span><span className="font-mono text-xs tabular-nums">MAE {v.mae_lf.toFixed(3)} · level {Math.round(v.level_acc * 100)}% · n {v.n}</span></li>)}</ul>
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
    return <tr key={k} className="border-t border-slate-200 dark:border-white/5"><td className="py-2 pr-6">{l}</td><td className="pr-6 text-right font-mono tabular-nums">{v.before.toLocaleString('en-IN')}</td><td className="pr-6 text-right font-mono tabular-nums">{v.after.toLocaleString('en-IN')}</td><td className="text-right font-mono font-bold text-emerald-700 dark:text-emerald-400">{v.change}</td></tr>
  }
  return (
    <Panel title="Impact if advisories are followed (computed by the twin)" right={<SimBadge source="twin" />}>
      <table className="text-sm">
        <thead><tr className="ledger text-left"><th className="pb-1 pr-6">Per simulated weekday (MTC routes)</th><th className="pr-6 text-right">Baseline</th><th className="pr-6 text-right">Advised</th><th className="text-right">Change</th></tr></thead>
        <tbody>
          {row('crowded_vehicle_stops_per_day', 'CROWDED vehicle-stops')}
          {row('left_behind_per_day', 'Passengers left behind')}
          {row('peak_lf_p90', 'Busiest-slot load factor (95th pct)')}
        </tbody>
      </table>
      <p className="font-mono text-xs text-slate-600 dark:text-slate-400">Cost: +{String(i.data.extra_trips_per_day)} trips, +{String(i.data.extra_bus_hours_per_day)} bus-hours per day.</p>
    </Panel>
  )
}

export default function Depot() {
  const routes = usePolling<RouteInfo[]>('/routes', 3600_000)
  const r = routes.data ?? []
  return (
    <div className="space-y-4">
      <h1 className="text-[28px] font-bold leading-tight text-[#002046] sm:text-[32px] dark:text-navy-soft">Depot dashboard</h1>
      <Heatmap />
      <Advisories />
      <ScenarioBuilder routes={r} />
      <div className="grid gap-4 xl:grid-cols-2"><DataHealth /><Impact /></div>
    </div>
  )
}
