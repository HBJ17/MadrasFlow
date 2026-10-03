// What-if simulator. Two independent panels: CONDITIONS (day, weather, events, disruptions, demand)
// and FLEET PLAN (extra buses per route and hour). Either one alone, or both, can be run through the
// digital twin; results compare the plan with a normal day of the same kind, and up to three results
// can be saved side by side.
import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getJSON, levelOf, postJSON, type RouteInfo } from '../../api'
import { SimBadge } from '../../components'
import { Panel, useChartColors } from './ui'

type DayType = 'weekday' | 'weekend' | 'holiday'
type Weather = 'dry' | 'light' | 'heavy' | 'cyclone'
type DisKind = 'metro_delay' | 'mrts_suspended' | 'bus_cut'
interface Ev { venue_stop: string; attendance: number; start: string; end: string }
interface Dis { kind: DisKind; from: string; to: string }
interface Conditions { day_type: DayType; weather: Weather; events: Ev[]; disruptions: Dis[]; demand_pct: number }
type Fleet = Record<string, number>          // `${route}|${hour}` -> extra buses
type Dirs = Record<string, number | null>    // route -> direction (null = both)

interface GridCell { route_id: string; direction: number; hour: number; lf: number }
interface Summary {
  hourly: { hour: number; lf_before: number; lf_after: number; left_behind_before: number; left_behind_after: number; crowded_before: number; crowded_after: number }[]
  scenario: Record<string, number>; baseline: Record<string, number>
  grid: { before: GridCell[]; after: GridCell[] }; worse_routes: string[]
  fleet: { bus_hours: number; trips_added: number; by_route: Record<string, { bus_hours: number; trips: number; peak_buses: number; round_trip_min: number }> } | null
}
interface RunResult { status: string; error?: string; summary?: Summary }
interface Saved { name: string; describe: string; summary: Summary }

const HOURS = Array.from({ length: 18 }, (_, i) => i + 5)            // 05:00 .. 22:00
const NORMAL: Conditions = { day_type: 'weekday', weather: 'dry', events: [], disruptions: [], demand_pct: 0 }
const VENUES: [string, string][] = [['MRTS_CHPK', 'Chepauk stadium'], ['CMRL_22', 'Guindy (trade centre)'], ['MRTS_VLCY', 'Velachery (malls)'],
  ['MRTS_TVMR', 'Thiruvanmiyur (beach)'], ['MRTS_STM', 'St. Thomas Mount'], ['CMRL_26', 'Airport']]
const DIS: Record<DisKind, string> = { metro_delay: 'Metro delays (half the trains)', mrts_suspended: 'MRTS suspended', bus_cut: 'Fewer buses (about a quarter off)' }
const WEATHER: Record<Weather, string> = { dry: 'Dry', light: 'Light rain', heavy: 'Heavy rain', cyclone: 'Cyclone' }
const KPIS: [string, string, boolean][] = [['left_behind_total', 'People left behind', true], ['crowded_vehicle_stops', 'Crowded bus-stops', true],
  ['unmet_demand', 'Gave up travelling', true], ['boardings_total', 'Boardings', false]]
const SAVE_KEY = 'mf-whatif-saved'
const NOISE = 10   // load-% points; one simulated day varies about this much hour to hour

const fmt = (n: number) => Math.round(n).toLocaleString('en-IN')
const hh = (h: number) => `${String(h).padStart(2, '0')}:00`

function conditionsChanged(c: Conditions) {
  return c.day_type !== 'weekday' || c.weather !== 'dry' || c.events.length > 0 || c.disruptions.length > 0 || c.demand_pct !== 0
}

function describe(c: Conditions, fleet: Fleet, routes: RouteInfo[]) {
  const parts: string[] = []
  if (c.day_type !== 'weekday') parts.push(c.day_type)
  if (c.weather !== 'dry') parts.push(WEATHER[c.weather].toLowerCase())
  c.events.forEach((e) => parts.push(`${VENUES.find((v) => v[0] === e.venue_stop)?.[1] ?? e.venue_stop} event (${fmt(e.attendance)})`))
  c.disruptions.forEach((d) => parts.push(`${DIS[d.kind].split(' (')[0].toLowerCase()} ${d.from}–${d.to}`))
  if (c.demand_pct) parts.push(`demand ${c.demand_pct > 0 ? '+' : ''}${c.demand_pct}%`)
  const byRoute: Record<string, number> = {}
  Object.entries(fleet).forEach(([k, n]) => { const r = k.split('|')[0]; byRoute[r] = (byRoute[r] ?? 0) + n })
  Object.entries(byRoute).forEach(([r, bh]) => parts.push(`+${bh} bus-hours on ${routes.find((x) => x.route_id === r)?.short_name ?? r}`))
  return parts.length ? parts.join(' · ') : 'no changes'
}

function Seg<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <fieldset>
      <legend className="ledger mb-1.5">{label}</legend>
      <div className="flex flex-wrap gap-1 rounded-xl bg-slate-100 p-1 dark:bg-[#1a1d25]">
        {options.map(([v, l]) => <button key={v} type="button" className="seg" aria-pressed={v === value} onClick={() => onChange(v)}>{l}</button>)}
      </div>
    </fieldset>
  )
}

function ConditionsPanel({ c, set }: { c: Conditions; set: (c: Conditions) => void }) {
  const [draft, setDraft] = useState<Ev>({ venue_stop: 'MRTS_CHPK', attendance: 35000, start: '15:30', end: '19:00' })
  const toggleDis = (k: DisKind) => set({ ...c, disruptions: c.disruptions.some((d) => d.kind === k) ? c.disruptions.filter((d) => d.kind !== k)
    : [...c.disruptions, { kind: k, from: k === 'metro_delay' ? '08:30' : '07:00', to: k === 'metro_delay' ? '10:00' : '11:00' }] })
  return (
    <div className="space-y-4">
      <Seg label="Day" value={c.day_type} options={[['weekday', 'Weekday'], ['weekend', 'Weekend'], ['holiday', 'Holiday']]} onChange={(v) => set({ ...c, day_type: v })} />
      <Seg label="Weather" value={c.weather} options={Object.entries(WEATHER) as [Weather, string][]} onChange={(v) => set({ ...c, weather: v })} />
      <fieldset className="space-y-2">
        <legend className="ledger">City events</legend>
        {c.events.map((e, i) => (
          <div key={i} className="flex items-center justify-between gap-2 rounded-lg bg-amber-100 px-3 py-2 text-sm text-amber-950 dark:bg-amber-400/15 dark:text-amber-200">
            <span>{VENUES.find((v) => v[0] === e.venue_stop)?.[1]} · {fmt(e.attendance)} people · {e.start}–{e.end}</span>
            <button type="button" className="tap px-2" aria-label="Remove event" onClick={() => set({ ...c, events: c.events.filter((_, j) => j !== i) })}>✕</button>
          </div>
        ))}
        {c.events.length < 3 ? (
          <div className="flex flex-wrap items-end gap-2">
            <label className="w-full text-xs sm:w-48">Venue
              <select className="input mt-1 text-sm" value={draft.venue_stop} onChange={(e) => setDraft({ ...draft, venue_stop: e.target.value })}>
                {VENUES.map(([id, n]) => <option key={id} value={id}>{n}</option>)}
              </select></label>
            <label className="w-40 text-xs">Crowd: {fmt(draft.attendance)}
              <input type="range" min={5000} max={60000} step={5000} className="mt-3 w-full accent-[#002046] dark:accent-lime" value={draft.attendance} onChange={(e) => setDraft({ ...draft, attendance: Number(e.target.value) })} /></label>
            <label className="text-xs">From<input type="time" className="input mt-1 w-28 text-sm" value={draft.start} onChange={(e) => setDraft({ ...draft, start: e.target.value })} /></label>
            <label className="text-xs">To<input type="time" className="input mt-1 w-28 text-sm" value={draft.end} onChange={(e) => setDraft({ ...draft, end: e.target.value })} /></label>
            <button type="button" className="btn-ghost whitespace-nowrap text-sm" onClick={() => set({ ...c, events: [...c.events, draft] })}>+ Add event</button>
          </div>
        ) : null}
      </fieldset>
      <fieldset className="space-y-2">
        <legend className="ledger">Disruptions</legend>
        {(Object.keys(DIS) as DisKind[]).map((k) => {
          const d = c.disruptions.find((x) => x.kind === k)
          return (
            <div key={k} className="flex flex-wrap items-center gap-2">
              <button type="button" aria-pressed={!!d} onClick={() => toggleDis(k)}
                className={`tap rounded-full px-3 font-display text-sm font-semibold ring-1 transition ${d ? 'brand-fill ring-transparent' : 'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-[#1e232e] dark:text-slate-300 dark:ring-white/10'}`}>{d ? '✓ ' : ''}{DIS[k]}</button>
              {d ? (
                <span className="flex items-center gap-1 text-sm">
                  <input aria-label={`${DIS[k]} from`} type="time" className="input w-28 text-sm" value={d.from}
                    onChange={(e) => set({ ...c, disruptions: c.disruptions.map((x) => (x.kind === k ? { ...x, from: e.target.value } : x)) })} />–
                  <input aria-label={`${DIS[k]} to`} type="time" className="input w-28 text-sm" value={d.to}
                    onChange={(e) => set({ ...c, disruptions: c.disruptions.map((x) => (x.kind === k ? { ...x, to: e.target.value } : x)) })} />
                </span>
              ) : null}
            </div>
          )
        })}
      </fieldset>
      <label className="ledger block">Demand <span className="text-[#002046] dark:text-navy-soft">{c.demand_pct > 0 ? '+' : ''}{c.demand_pct}%</span>
        <input type="range" min={-30} max={30} step={5} className="mt-2 w-full accent-[#002046] dark:accent-lime" value={c.demand_pct} onChange={(e) => set({ ...c, demand_pct: Number(e.target.value) })} />
      </label>
    </div>
  )
}

function FleetPanel({ routes, fleet, setFleet, dirs, setDirs }: { routes: RouteInfo[]; fleet: Fleet; setFleet: (f: Fleet) => void; dirs: Dirs; setDirs: (d: Dirs) => void }) {
  const [tool, setTool] = useState<'add' | 'remove'>('add')
  const buses = routes.filter((r) => r.mode === 'bus')
  const tap = (rid: string, h: number) => {
    const k = `${rid}|${h}`
    const n = Math.max(0, Math.min(5, (fleet[k] ?? 0) + (tool === 'add' ? 1 : -1)))
    const f = { ...fleet }
    if (n) f[k] = n; else delete f[k]
    setFleet(f)
  }
  const busHours = Object.values(fleet).reduce((a, b) => a + b, 0)
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-[#1a1d25]" role="group" aria-label="Tap tool">
          <button type="button" className="seg" aria-pressed={tool === 'add'} onClick={() => setTool('add')}>+ Add bus</button>
          <button type="button" className="seg" aria-pressed={tool === 'remove'} onClick={() => setTool('remove')}>− Remove</button>
        </div>
        <span className="text-sm text-slate-600 dark:text-slate-400">Tap an hour to {tool === 'add' ? 'add' : 'remove'} one bus · up to 5 per hour</span>
      </div>
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-0.5 text-xs">
          <thead className="font-mono"><tr><th className="px-1 text-left">Route</th>{HOURS.map((h) => <th key={h} className="w-8 font-normal tabular-nums">{String(h).padStart(2, '0')}</th>)}</tr></thead>
          <tbody>
            {buses.map((r) => (
              <tr key={r.route_id}>
                <th className="whitespace-nowrap px-1 text-left font-medium">
                  <div className="font-display font-bold text-[#002046] dark:text-navy-soft">{r.short_name}</div>
                  <select aria-label={`${r.short_name} direction`} className="mt-0.5 rounded bg-transparent text-[11px] font-normal text-slate-600 dark:text-slate-400"
                    value={dirs[r.route_id] == null ? 'b' : String(dirs[r.route_id])}
                    onChange={(e) => setDirs({ ...dirs, [r.route_id]: e.target.value === 'b' ? null : Number(e.target.value) })}>
                    <option value="b">both ways</option>
                    {r.directions.map((d) => <option key={d.direction} value={d.direction}>→ {d.to}</option>)}
                  </select>
                </th>
                {HOURS.map((h) => {
                  const n = fleet[`${r.route_id}|${h}`] ?? 0
                  return (
                    <td key={h} className="p-0">
                      <button type="button" onClick={() => tap(r.route_id, h)} aria-label={`${r.short_name} at ${hh(h)}: ${n} extra bus${n === 1 ? '' : 'es'}`}
                        className={`h-9 w-8 rounded-md font-mono text-xs font-bold tabular-nums ring-1 transition ${n ? 'brand-fill ring-transparent' : 'bg-white ring-slate-200 hover:bg-teal-50 dark:bg-slate-950 dark:ring-white/10 dark:hover:bg-slate-800'}`}>
                        {n ? `+${n}` : ''}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-sm">{busHours ? <>Added: <b>{busHours} bus-hours</b>. The twin turns buses into trips using each route's round-trip time.</> : <span className="text-slate-600 dark:text-slate-400">No buses added.</span>}</p>
    </div>
  )
}

function GridView({ s, routes }: { s: Summary; routes: RouteInfo[] }) {
  const [mode, setMode] = useState<'before' | 'after' | 'diff'>('diff')
  const { rows, hours, b, a } = useMemo(() => {
    const key = (x: GridCell) => `${x.route_id}|${x.direction}|${x.hour}`
    const b = new Map(s.grid.before.map((x) => [key(x), x.lf]))
    const a = new Map(s.grid.after.map((x) => [key(x), x.lf]))
    const rows = [...new Set(s.grid.before.concat(s.grid.after).map((x) => `${x.route_id}|${x.direction}`))].sort()
    const hours = [...new Set(s.grid.before.concat(s.grid.after).map((x) => x.hour))].sort((p, q) => p - q)
    return { rows, hours, b, a }
  }, [s])
  const name = (k: string) => {
    const [rid, d] = k.split('|')
    const r = routes.find((x) => x.route_id === rid)
    return `${r?.short_name ?? rid} → ${r?.directions.find((x) => x.direction === Number(d))?.to ?? d}`
  }
  return (
    <figure className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <figcaption className="ledger">Busiest 10% of bus-stops in each hour (load %)</figcaption>
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-[#1a1d25]" role="group" aria-label="Heatmap view">
          <button type="button" className="seg" aria-pressed={mode === 'before'} onClick={() => setMode('before')}>Before</button>
          <button type="button" className="seg" aria-pressed={mode === 'after'} onClick={() => setMode('after')}>After</button>
          <button type="button" className="seg" aria-pressed={mode === 'diff'} onClick={() => setMode('diff')}>Difference</button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-0.5 text-xs">
          <thead className="font-mono"><tr><th className="px-2 text-left">Route</th>{hours.map((h) => <th key={h} className="px-1 font-normal tabular-nums">{String(h).padStart(2, '0')}</th>)}</tr></thead>
          <tbody>
            {rows.map((k) => (
              <tr key={k}>
                <th className="whitespace-nowrap px-2 text-left font-medium">{name(k)}</th>
                {hours.map((h) => {
                  const vb = b.get(`${k}|${h}`), va = a.get(`${k}|${h}`)
                  if (mode !== 'diff') {
                    const v = mode === 'before' ? vb : va
                    return <td key={h} className={`lvl-${levelOf(v ?? null) ?? 'none'} rounded px-1 py-1 text-center tabular-nums`} title={`${name(k)} ${hh(h)}: ${v != null ? Math.round(v * 100) + '%' : 'no service'}`}>{v != null ? Math.round(v * 100) : ''}</td>
                  }
                  if (vb == null && va == null) return <td key={h} className="lvl-none rounded" />
                  const d = Math.round(((va ?? 0) - (vb ?? 0)) * 100)
                  const cls = d <= -NOISE ? 'bg-emerald-600 text-white' : d >= NOISE ? 'bg-red-700 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'
                  return <td key={h} className={`${cls} rounded px-1 py-1 text-center tabular-nums`} title={`${name(k)} ${hh(h)}: ${vb != null ? Math.round(vb * 100) : '–'}% → ${va != null ? Math.round(va * 100) : '–'}%`}>{d > 0 ? `+${d}` : d}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {mode === 'diff' ? <p className="text-xs text-slate-600 dark:text-slate-400">Green = at least 10 points less crowded with the plan, red = at least 10 points more, grey = about the same. Smaller changes are within the normal variation of a single simulated day.</p> : null}
    </figure>
  )
}

function ChartBox({ title, children }: { title: string; children: React.ReactElement }) {
  return (
    <figure className="space-y-1">
      <figcaption className="ledger">{title}</figcaption>
      <div className="h-56"><ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer></div>
    </figure>
  )
}

function Results({ s, routes, onSave, canSave }: { s: Summary; routes: RouteInfo[]; onSave: () => void; canSave: boolean }) {
  const C = useChartColors()
  return (
    <div className="space-y-4 border-t border-slate-200 pt-4 dark:border-white/5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-[#002046] dark:text-navy-soft">Result · plan vs a normal day of the same kind</h3>
        <button type="button" className="btn-ghost text-sm" onClick={onSave} disabled={!canSave}>☆ Save to compare</button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {KPIS.map(([k, l, lowerBetter]) => {
          const b = Number(s.baseline[k] ?? 0), a = Number(s.scenario[k] ?? 0)
          const ch = b ? Math.round((a / b - 1) * 100) : 0
          const good = lowerBetter ? ch < 0 : ch > 0
          return (
            <div key={k} className="rounded-xl bg-paper p-3 ring-1 ring-slate-200 dark:bg-slate-950 dark:ring-white/5">
              <div className="ledger text-[10px]">{l}</div>
              <div className="mt-1 font-display text-2xl font-bold tabular-nums text-[#002046] dark:text-navy-soft">{fmt(a)}</div>
              <div className="font-mono text-[11px] tabular-nums text-slate-600 dark:text-slate-400">
                normal day {fmt(b)} · <span className={ch === 0 ? '' : good ? 'font-semibold text-emerald-700 dark:text-emerald-400' : 'font-semibold text-red-700 dark:text-red-400'}>{ch > 0 ? '+' : ''}{ch}%</span>
              </div>
            </div>
          )
        })}
        <div className="rounded-xl bg-paper p-3 ring-1 ring-slate-200 dark:bg-slate-950 dark:ring-white/5">
          <div className="ledger text-[10px]">Fleet cost</div>
          <div className="mt-1 font-display text-2xl font-bold tabular-nums text-[#002046] dark:text-navy-soft">{s.fleet ? `${s.fleet.bus_hours} bus-h` : '–'}</div>
          <div className="font-mono text-[11px] text-slate-600 dark:text-slate-400">{s.fleet ? `${s.fleet.trips_added} extra trips` : 'no buses added'}</div>
        </div>
      </div>
      {s.worse_routes.length ? (
        <p role="status" className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-300 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-700">
          ⚠ Busier with this plan: {s.worse_routes.map((r) => routes.find((x) => x.route_id === r)?.short_name ?? r).join(', ')} (their busiest hours rise by more than 8 points).
        </p>
      ) : null}
      <GridView s={s} routes={routes} />
      <div className="grid gap-4 lg:grid-cols-3">
        <ChartBox title="Load factor (busiest 10%) by hour">
          <LineChart data={s.hourly}><CartesianGrid strokeDasharray="3 3" stroke={C.grid} /><XAxis dataKey="hour" /><YAxis domain={[0, 'auto']} />
            <Tooltip /><Legend /><ReferenceLine y={1} stroke="#ba1a1a" strokeDasharray="4 4" />
            <Line dataKey="lf_before" name="normal day" stroke={C.before} dot={false} strokeWidth={2.5} strokeDasharray="5 3" isAnimationActive={false} />
            <Line dataKey="lf_after" name="with plan" stroke={C.after} dot={false} strokeWidth={2.5} isAnimationActive={false} /></LineChart>
        </ChartBox>
        <ChartBox title="People left behind by hour">
          <BarChart data={s.hourly}><CartesianGrid strokeDasharray="3 3" stroke={C.grid} /><XAxis dataKey="hour" /><YAxis /><Tooltip /><Legend />
            <Bar dataKey="left_behind_before" name="normal day" fill={C.before} isAnimationActive={false} /><Bar dataKey="left_behind_after" name="with plan" fill={C.after} isAnimationActive={false} /></BarChart>
        </ChartBox>
        <ChartBox title="Crowded bus-stops by hour">
          <BarChart data={s.hourly}><CartesianGrid strokeDasharray="3 3" stroke={C.grid} /><XAxis dataKey="hour" /><YAxis /><Tooltip /><Legend />
            <Bar dataKey="crowded_before" name="normal day" fill={C.before} isAnimationActive={false} /><Bar dataKey="crowded_after" name="with plan" fill={C.after} isAnimationActive={false} /></BarChart>
        </ChartBox>
      </div>
    </div>
  )
}

function Compare({ saved, onRemove }: { saved: Saved[]; onRemove: (i: number) => void }) {
  if (!saved.length) return null
  const best = (k: string, lower: boolean) => {
    const v = saved.map((p) => Number(p.summary.scenario[k] ?? 0))
    return lower ? Math.min(...v) : Math.max(...v)
  }
  return (
    <div className="space-y-2 border-t border-slate-200 pt-4 dark:border-white/5">
      <h3 className="text-lg font-semibold text-[#002046] dark:text-navy-soft">Saved plans</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="ledger text-left"><th className="py-1 pr-4">Plan</th>{KPIS.slice(0, 3).map(([, l]) => <th key={l} className="pr-4 text-right">{l}</th>)}<th className="pr-4 text-right">Bus-hours</th><th /></tr></thead>
          <tbody>
            {saved.map((p, i) => (
              <tr key={i} className="border-t border-slate-200 dark:border-white/5">
                <td className="py-2 pr-4"><b>{p.name}</b><div className="text-xs text-slate-600 dark:text-slate-400">{p.describe}</div></td>
                {KPIS.slice(0, 3).map(([k]) => {
                  const v = Number(p.summary.scenario[k] ?? 0)
                  return <td key={k} className={`pr-4 text-right font-mono tabular-nums ${saved.length > 1 && v === best(k, true) ? 'font-bold text-emerald-700 dark:text-emerald-400' : ''}`}>{fmt(v)}</td>
                })}
                <td className="pr-4 text-right font-mono tabular-nums">{p.summary.fleet?.bus_hours ?? 0}</td>
                <td><button type="button" className="tap px-2" aria-label={`Remove ${p.name}`} onClick={() => onRemove(i)}>✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function ScenarioBuilder({ routes }: { routes: RouteInfo[] }) {
  const [cond, setCond] = useState<Conditions>(NORMAL)
  const [fleet, setFleet] = useState<Fleet>({})
  const [dirs, setDirs] = useState<Dirs>({})
  const [runId, setRunId] = useState<string | null>(null)
  const [res, setRes] = useState<RunResult | null>(null)
  const [ranWith, setRanWith] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [saved, setSaved] = useState<Saved[]>(() => { try { return JSON.parse(localStorage.getItem(SAVE_KEY) || '[]') } catch { return [] } })
  useEffect(() => { try { localStorage.setItem(SAVE_KEY, JSON.stringify(saved)) } catch { /* storage may be unavailable */ } }, [saved])

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

  const condOn = conditionsChanged(cond)
  const fleetOn = Object.keys(fleet).length > 0
  const running = res?.status === 'queued' || res?.status === 'running'

  const preset = (p: 'monsoon' | 'cricket' | 'cyclone' | 'boost95') => {
    if (p === 'monsoon') setCond({ ...NORMAL, weather: 'heavy' })
    if (p === 'cricket') setCond({ ...NORMAL, events: [{ venue_stop: 'MRTS_CHPK', attendance: 35000, start: '15:30', end: '19:00' }] })
    if (p === 'cyclone') setCond({ ...NORMAL, weather: 'cyclone' })
    if (p === 'boost95') setFleet({ ...fleet, 'BUS_95|8': 2, 'BUS_95|9': 2, 'BUS_95|17': 2, 'BUS_95|18': 2 })
  }

  const run = async () => {
    setErr(null); setRes({ status: 'queued' })
    const mods: Record<string, unknown> = {}
    if (condOn) Object.assign(mods, { day_type: cond.day_type, weather: cond.weather, events: cond.events, disruptions: cond.disruptions, demand_pct: cond.demand_pct })
    if (fleetOn) mods.fleet = Object.entries(fleet).map(([k, n]) => { const [route, h] = k.split('|'); return { route, direction: dirs[route] ?? null, hour: Number(h), buses: n } })
    try {
      const { data } = await postJSON<{ run_id: string }>('/twin/run', { scenario: 'builder', days: 1, seed: 42, mods })
      setRanWith(describe(condOn ? cond : NORMAL, fleetOn ? fleet : {}, routes))
      setRunId(data.run_id)
    } catch (e) { setErr(String((e as Error).message)); setRes(null) }
  }
  const save = () => {
    if (!res?.summary) return
    const name = `Plan ${String.fromCharCode(65 + (saved.length ? saved.length : 0))}`
    setSaved([...saved, { name, describe: ranWith, summary: res.summary }].slice(-3))
  }

  return (
    <Panel title="What-if simulator · test plans in the digital twin" right={<SimBadge source="twin" />}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="ledger">Quick start:</span>
        <button type="button" className="btn-ghost text-sm" onClick={() => preset('monsoon')}>🌧 Monsoon morning</button>
        <button type="button" className="btn-ghost text-sm" onClick={() => preset('cricket')}>🏏 Cricket at Chepauk</button>
        <button type="button" className="btn-ghost text-sm" onClick={() => preset('cyclone')}>🌀 Cyclone day</button>
        <button type="button" className="btn-ghost text-sm" onClick={() => preset('boost95')}>🚌 Peak boost on 95</button>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className={`space-y-3 rounded-xl bg-paper p-4 ring-1 dark:bg-slate-950 ${condOn ? 'ring-2 ring-brand' : 'ring-slate-200 dark:ring-white/5'}`} aria-labelledby="cond-h">
          <div className="flex items-center justify-between gap-2">
            <h3 id="cond-h" className="font-semibold text-[#002046] dark:text-navy-soft">Conditions {condOn ? <span className="ml-1 rounded-md bg-lime px-1.5 py-0.5 align-middle font-mono text-[10px] font-bold uppercase tracking-wider text-lime-ink">in this run</span> : <span className="ml-1 text-xs font-normal text-slate-600 dark:text-slate-400">normal day</span>}</h3>
            <button type="button" className="btn-ghost text-sm" onClick={() => setCond(NORMAL)} disabled={!condOn}>Clear</button>
          </div>
          <ConditionsPanel c={cond} set={setCond} />
        </section>
        <section className={`space-y-3 rounded-xl bg-paper p-4 ring-1 dark:bg-slate-950 ${fleetOn ? 'ring-2 ring-brand' : 'ring-slate-200 dark:ring-white/5'}`} aria-labelledby="fleet-h">
          <div className="flex items-center justify-between gap-2">
            <h3 id="fleet-h" className="font-semibold text-[#002046] dark:text-navy-soft">Fleet plan {fleetOn ? <span className="ml-1 rounded-md bg-lime px-1.5 py-0.5 align-middle font-mono text-[10px] font-bold uppercase tracking-wider text-lime-ink">in this run</span> : <span className="ml-1 text-xs font-normal text-slate-600 dark:text-slate-400">current timetable</span>}</h3>
            <button type="button" className="btn-ghost text-sm" onClick={() => setFleet({})} disabled={!fleetOn}>Clear</button>
          </div>
          <FleetPanel routes={routes} fleet={fleet} setFleet={setFleet} dirs={dirs} setDirs={setDirs} />
        </section>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-primary" onClick={run} disabled={running || (!condOn && !fleetOn)}>▶ Run simulation</button>
        <span className="text-sm text-slate-600 dark:text-slate-400">
          {!condOn && !fleetOn ? 'Set some conditions, add buses, or both.' : `This run: ${describe(condOn ? cond : NORMAL, fleetOn ? fleet : {}, routes)}`}
        </span>
      </div>
      {err ? <p role="alert" className="text-sm text-red-700 dark:text-red-400">{err}</p> : null}
      {running ? <div role="status" className="flex items-center gap-3 text-sm"><span className="h-2 w-40 animate-pulse rounded-full bg-emerald-400" /> Simulating a normal day and your plan (about 30–60 s)…</div> : null}
      {res?.status === 'error' ? <p className="text-sm text-red-700 dark:text-red-400">Twin run failed: {res.error}</p> : null}
      {res?.summary ? <Results s={res.summary} routes={routes} onSave={save} canSave={!saved.some((p) => p.summary === res.summary)} /> : null}
      <Compare saved={saved} onRemove={(i) => setSaved(saved.filter((_, j) => j !== i))} />
    </Panel>
  )
}
