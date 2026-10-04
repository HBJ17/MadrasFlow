// Fleet heatmap: routes x next 3 h, with a drill-down per route by stop (stops x time) or by bus
// (each scheduled trip x the stops it passes). Values are forecast estimates, not live counts.
// "With accepted changes" applies the twin-tested effect of the accepted recommendations.
import { useEffect, useState } from 'react'
import { hhmm, usePolling, type DataSource, type Level } from '../../api'
import { SimBadge } from '../../components'
import { ACCEPTED_EVENT, Panel, type EffectStatus } from './ui'

type Apply = 'none' | 'accepted'
interface Cell { lf: number; lo: number | null; hi: number | null; level: Level; people: number | null; stop?: string; at?: string; was?: number }
interface RouteHead { route_id: string; direction: number; route: string; mode: string; depot: string; capacity: number; from: string; to: string }
interface Overview { made_at: string | null; slots: string[]; rows: (RouteHead & { cells: (Cell | null)[] })[]; data_source: DataSource }
interface ByStop extends RouteHead { view: 'stops'; slots: string[]; rows: { stop_id: string; name: string; cells: (Cell | null)[] }[]; data_source: DataSource }
interface ByBus extends RouteHead { view: 'buses'; stops: { stop_id: string; name: string }[]; rows: { trip_id: string; vehicle_id: string; start: string; cells: (Cell | null)[] }[]; data_source: DataSource }

const pct = (x: number) => `${Math.round(x * 100)}%`
const tip = (c: Cell, where: string, cap: number) =>
  `${where}: ${pct(c.lf)} (${c.level.toLowerCase()})` +
  `${c.was != null ? `, was ${pct(c.was)} before the accepted changes` : ''}` +
  `${c.people != null ? `, about ${c.people} people for ${cap} places` : ''}` +
  `${c.lo != null && c.hi != null ? `, likely ${Math.round(c.lo * 100)}–${Math.round(c.hi * 100)}%` : ''}`

function HeatCell({ c, label, cap }: { c: Cell | null; label: string; cap: number }) {
  if (!c) return <td className="lvl-none rounded" aria-label={`${label}: no forecast`} />
  const changed = c.was != null && Math.round(c.was * 100) !== Math.round(c.lf * 100)
  return (
    <td className={`lvl-${c.level} rounded px-1 py-1.5 text-center font-mono text-[11px] font-semibold tabular-nums ${changed ? 'changed-cell' : ''}`} title={tip(c, label, cap)}>
      {Math.round(c.lf * 100)}{changed ? <span className="text-[9px]" aria-hidden="true">{c.lf < c.was! ? '↓' : '↑'}</span> : null}
    </td>
  )
}

function Legend({ apply }: { apply: Apply }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
      {(['LOW', 'MEDIUM', 'HIGH', 'CROWDED'] as Level[]).map((l) => <span key={l} className={`lvl-${l} rounded-md px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider`}>{l.toLowerCase()}</span>)}
      {apply === 'accepted' ? <span className="changed-cell rounded-md px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider">↓↑ changed</span> : null}
      <span className="font-mono text-[11px]">% = people on board + left behind ÷ capacity</span>
    </div>
  )
}

function Drill({ head, onClose, apply, t }: { head: RouteHead; onClose: () => void; apply: Apply; t: string }) {
  const [view, setView] = useState<'stops' | 'buses'>('stops')
  const d = usePolling<ByStop | ByBus>(`/fleet/heatmap/${head.route_id}?direction=${head.direction}&view=${view}&apply=${apply}${t ? `&t=${encodeURIComponent(t)}` : ''}`, 60_000)
  const data = d.data && d.data.view === view ? d.data : null
  const unit = head.mode === 'bus' ? 'bus' : 'train'
  const Unit = unit === 'bus' ? 'Bus' : 'Train'
  return (
    <div className="space-y-3 rounded-xl bg-paper p-3 ring-1 ring-slate-200 sm:p-4 dark:bg-slate-950 dark:ring-white/10">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-[#002046] dark:text-navy-soft">{head.route} · {head.from} → {head.to} <span className="font-normal text-slate-600 dark:text-slate-400">({head.depot} depot)</span></h3>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-[#1a1d25]" role="group" aria-label="Drill-down view">
            <button type="button" className="seg whitespace-nowrap" aria-pressed={view === 'stops'} onClick={() => setView('stops')}>By stop</button>
            <button type="button" className="seg whitespace-nowrap" aria-pressed={view === 'buses'} onClick={() => setView('buses')}>By {unit}</button>
          </div>
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>Close</button>
        </div>
      </div>
      {!data ? <p className="ledger">Loading…</p> : data.view === 'stops' ? (
        <div className="max-h-[28rem] overflow-auto">
          <table className="border-separate border-spacing-0.5 text-xs">
            <thead className="sticky top-0 z-10 bg-paper font-mono dark:bg-slate-950"><tr><th className="sticky left-0 bg-paper px-2 text-left dark:bg-slate-950">Stop</th>{data.slots.map((s) => <th key={s} className="min-w-9 px-1 font-normal tabular-nums">{hhmm(s)}</th>)}</tr></thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={r.stop_id}>
                  <th className="sticky left-0 whitespace-nowrap bg-paper px-2 text-left font-medium dark:bg-slate-950"><span className="mr-1.5 inline-block w-4 text-right font-mono text-slate-500 tabular-nums">{i + 1}</span>{r.name}</th>
                  {r.cells.map((c, j) => <HeatCell key={j} c={c} label={`${r.name} ${hhmm(data.slots[j])}`} cap={head.capacity} />)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="max-h-[34rem] overflow-auto">
          {!data.rows.length ? <p className="text-sm text-slate-600 dark:text-slate-400">No trips run in the forecast window.</p> : (
            <table className="border-separate border-spacing-0.5 text-xs">
              <thead className="sticky top-0 z-10 bg-paper dark:bg-slate-950">
                <tr>
                  <th className="sticky left-0 z-10 bg-paper px-2 pb-1 text-left align-bottom font-mono dark:bg-slate-950">{Unit} (leaves)</th>
                  {data.stops.map((s, i) => (
                    <th key={s.stop_id} scope="col" className="w-10 min-w-10 px-0 pb-1 align-bottom font-medium" title={s.name}>
                      <span className="mx-auto block max-h-40 overflow-hidden text-ellipsis whitespace-nowrap text-left [transform:rotate(180deg)] [writing-mode:vertical-rl]">
                        <span className="font-mono text-slate-500">{i + 1} </span>{s.name}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.trip_id}>
                    <th className="sticky left-0 whitespace-nowrap bg-paper px-2 text-left font-mono font-medium tabular-nums dark:bg-slate-950">
                      {hhmm(r.start)} <span className="font-normal text-slate-500">{r.vehicle_id.split('-').pop()}</span>
                    </th>
                    {r.cells.map((c, j) => <HeatCell key={j} c={c} label={`${hhmm(r.start)} ${unit} at ${data.stops[j].name}${c?.at ? ` (ETA : ${hhmm(c.at)})` : ''}`} cap={head.capacity} />)}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
            Columns are stops in order; hover a cell for the {unit}'s arrival time (ETA) and load. Blank cells fall outside the 3-hour forecast.
            {apply === 'accepted' ? ` Rows are today's timetable; extra ${unit === 'bus' ? 'buses' : 'trains'} from accepted changes are not drawn as rows, their relief shows in the cells.` : ''}
          </p>
        </div>
      )}
    </div>
  )
}

const n = (x: number) => x.toLocaleString('en-IN')

function EffectBar({ e, apply, setApply }: { e: EffectStatus | null; apply: Apply; setApply: (a: Apply) => void }) {
  const count = e?.accepted.length ?? 0
  const s = e?.status === 'ready' ? e.summary : null
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-[#1a1d25]" role="group" aria-label="Heatmap view">
          <button type="button" className="seg flex-none whitespace-nowrap" aria-pressed={apply === 'none'} onClick={() => setApply('none')}>Forecast</button>
          <button type="button" className="seg flex-none whitespace-nowrap" aria-pressed={apply === 'accepted'} disabled={!count} onClick={() => setApply('accepted')}
            title={count ? undefined : 'Accept a recommendation to see its effect here'}>
            With accepted changes{count ? ` (${count})` : ''}
          </button>
        </div>
        {e?.status === 'computing' ? <span className="text-sm text-amber-700 dark:text-amber-300" role="status">Testing {count} accepted change{count === 1 ? '' : 's'} in the twin… (about a minute)</span> : null}
        {e?.status === 'error' ? <span className="text-sm text-red-700 dark:text-red-400" role="alert">Twin test failed: {e.error}</span> : null}
      </div>
      {apply === 'accepted' && s ? (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-950 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-100 dark:ring-emerald-800">
          With {count} accepted change{count === 1 ? '' : 's'} (tested together in the twin at {hhmm(s.computed_at)}{s.trips_added ? `, ${s.trips_added} extra trips` : ''}),
          over the whole day: people left behind <b>{n(s.left_behind_total.before)} → {n(s.left_behind_total.after)}</b>,
          crowded bus-stops <b>{n(s.crowded_vehicle_stops.before)} → {n(s.crowded_vehicle_stops.after)}</b>,
          people who gave up <b>{n(s.unmet_demand.before)} → {n(s.unmet_demand.after)}</b>.
          {' '}Outlined cells changed ({s.cells} stop-slots today); hover one for its value before.
          {s.skipped.length ? ` ${s.skipped.length} recommendation(s) could not be tested.` : ''}
        </p>
      ) : null}
      {apply === 'accepted' && !s && e?.status !== 'computing' ? <p className="text-sm text-slate-600 dark:text-slate-400">No tested changes yet; showing the plain forecast.</p> : null}
    </div>
  )
}

export default function Heatmap() {
  const [apply, setApply] = useState<Apply>('none')
  const eff = usePolling<EffectStatus>('/fleet/effect', 5_000)
  const e = eff.data
  // "with changes" only once the twin result for the current accepted set is in; the result's time is
  // part of the URL so a new result is fetched at once
  const t = apply === 'accepted' && e?.status === 'ready' && e.summary ? e.summary.computed_at : ''
  const effective: Apply = t ? 'accepted' : 'none'
  const o = usePolling<Overview>(`/fleet/heatmap?apply=${effective}${t ? `&t=${encodeURIComponent(t)}` : ''}`, 60_000)
  const [open, setOpen] = useState<RouteHead | null>(null)
  const d = o.data
  const { reload: reloadEff } = eff
  useEffect(() => {
    // accepting a recommendation switches to the "with changes" view and checks progress straight away
    const on = (ev: Event) => { reloadEff(); if ((ev as CustomEvent).detail === 'accept') setApply('accepted') }
    window.addEventListener(ACCEPTED_EVENT, on)
    return () => window.removeEventListener(ACCEPTED_EVENT, on)
  }, [reloadEff])
  useEffect(() => { if (e && !e.accepted.length) setApply('none') }, [e])
  return (
    <Panel title="Fleet heatmap · next 3 hours" right={<SimBadge source={d?.data_source} />}>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Estimated crowding in 15-minute steps from the forecast model trained on the digital twin, refreshed every 5 minutes; not live counts.
        Each cell is the busiest stop on that route. Click a route to see every stop or every bus.
      </p>
      <EffectBar e={e} apply={apply} setApply={setApply} />
      {!d?.rows.length ? <p className="text-sm text-slate-600 dark:text-slate-400">{o.loading ? 'Loading forecast…' : 'No forecast yet. The forecast job runs every 5 minutes.'}</p> : (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0.5 text-xs">
            <thead className="font-mono"><tr><th className="sticky left-0 bg-card px-2 text-left">Route</th>{d.slots.map((s) => <th key={s} className="px-1 font-normal tabular-nums">{hhmm(s)}</th>)}</tr></thead>
            <tbody>
              {d.rows.map((r) => {
                const sel = open?.route_id === r.route_id && open.direction === r.direction
                return (
                  <tr key={`${r.route_id}|${r.direction}`}>
                    <th className="sticky left-0 bg-card px-1 text-left font-medium">
                      <button type="button" aria-expanded={sel} onClick={() => setOpen(sel ? null : r)}
                        className={`tap w-full whitespace-nowrap rounded-lg px-1 text-left hover:bg-slate-100 dark:hover:bg-slate-800 ${sel ? 'font-semibold text-brand underline dark:text-teal-300' : ''}`}>
                        {r.route} → {r.to}
                      </button>
                    </th>
                    {r.cells.map((c, j) => <HeatCell key={j} c={c} label={`${r.route} → ${r.to} ${hhmm(d.slots[j])}${c?.stop ? ` at ${c.stop}` : ''}`} cap={r.capacity} />)}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <Legend apply={effective} />
      {open ? <Drill key={`${open.route_id}|${open.direction}`} head={open} onClose={() => setOpen(null)} apply={effective} t={t} /> : null}
    </Panel>
  )
}
