// Fleet heatmap: routes x next 3 h, with a drill-down per route by stop (stops x time) or by bus
// (each scheduled trip x the stops it passes). Values are forecast estimates, not live counts.
import { useState } from 'react'
import { hhmm, usePolling, type DataSource, type Level } from '../../api'
import { SimBadge } from '../../components'
import { Panel } from './ui'

interface Cell { lf: number; lo: number | null; hi: number | null; level: Level; people: number | null; stop?: string; at?: string }
interface RouteHead { route_id: string; direction: number; route: string; mode: string; depot: string; capacity: number; from: string; to: string }
interface Overview { made_at: string | null; slots: string[]; rows: (RouteHead & { cells: (Cell | null)[] })[]; data_source: DataSource }
interface ByStop extends RouteHead { view: 'stops'; slots: string[]; rows: { stop_id: string; name: string; cells: (Cell | null)[] }[]; data_source: DataSource }
interface ByBus extends RouteHead { view: 'buses'; stops: { stop_id: string; name: string }[]; rows: { trip_id: string; vehicle_id: string; start: string; cells: (Cell | null)[] }[]; data_source: DataSource }

const tip = (c: Cell, where: string, cap: number) =>
  `${where}: ${Math.round(c.lf * 100)}% (${c.level.toLowerCase()})` +
  `${c.people != null ? `, about ${c.people} people for ${cap} places` : ''}` +
  `${c.lo != null && c.hi != null ? `, likely ${Math.round(c.lo * 100)}–${Math.round(c.hi * 100)}%` : ''}`

function HeatCell({ c, label, cap }: { c: Cell | null; label: string; cap: number }) {
  if (!c) return <td className="lvl-none rounded" aria-label={`${label}: no forecast`} />
  return (
    <td className={`lvl-${c.level} rounded px-1 py-1.5 text-center font-mono text-[11px] font-semibold tabular-nums`} title={tip(c, label, cap)}>
      {Math.round(c.lf * 100)}
    </td>
  )
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
      {(['LOW', 'MEDIUM', 'HIGH', 'CROWDED'] as Level[]).map((l) => <span key={l} className={`lvl-${l} rounded-md px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider`}>{l.toLowerCase()}</span>)}
      <span className="font-mono text-[11px]">% = people on board + left behind ÷ capacity</span>
    </div>
  )
}

function Drill({ head, onClose }: { head: RouteHead; onClose: () => void }) {
  const [view, setView] = useState<'stops' | 'buses'>('stops')
  const d = usePolling<ByStop | ByBus>(`/fleet/heatmap/${head.route_id}?direction=${head.direction}&view=${view}`, 60_000)
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
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">Columns are stops in order; hover a cell for the {unit}'s arrival time (ETA) and load. Blank cells fall outside the 3-hour forecast.</p>
        </div>
      )}
    </div>
  )
}

export default function Heatmap() {
  const o = usePolling<Overview>('/fleet/heatmap', 60_000)
  const [open, setOpen] = useState<RouteHead | null>(null)
  const d = o.data
  return (
    <Panel title="Fleet heatmap · next 3 hours" right={<SimBadge source={d?.data_source} />}>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Estimated crowding in 15-minute steps from the forecast model trained on the digital twin, refreshed every 5 minutes; not live counts.
        Each cell is the busiest stop on that route. Click a route to see every stop or every bus.
      </p>
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
      <Legend />
      {open ? <Drill key={`${open.route_id}|${open.direction}`} head={open} onClose={() => setOpen(null)} /> : null}
    </Panel>
  )
}
