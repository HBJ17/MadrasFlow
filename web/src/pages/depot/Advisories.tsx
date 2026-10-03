// Recommendations read from the heatmap: add trips (twin-tested), short-turn, move a bus between
// routes, and hold a bus for arriving trains. Each card says why, what to do, and what it costs.
import { useState } from 'react'
import { hhmm, levelOf, postJSON, usePolling, type DataSource } from '../../api'
import { LevelChip, SimBadge } from '../../components'
import { Panel } from './ui'

type Kind = 'add_trips' | 'short_turn' | 'move_bus' | 'hold_for_train'
interface Advisory {
  advisory_id: number; route: string; route_id: string; direction: number; depot: string; slot_start: string; slot_end: string
  reason: string; action: string; extra_trips: number; expected_lf_before: number | null; expected_lf_after: number | null
  neighbour_lf_after: number | null; extra_vehicle_hours: number | null; status: string; created_at: string; kind: Kind | null
}

const KIND: Record<Kind, { label: string; icon: string; check: string }> = {
  add_trips: { label: 'Add trips', icon: '➕', check: 'Tested in the twin' },
  short_turn: { label: 'Short-turn', icon: '↩', check: 'Same capacity as the twin-tested extra trips, on the crowded section only' },
  move_bus: { label: 'Move a bus', icon: '⇄', check: 'Estimated from the forecast; the quiet route stays below the figure shown' },
  hold_for_train: { label: 'Hold for train', icon: '⏸', check: 'Estimate: not tested in the twin' },
}

export default function Advisories() {
  const a = usePolling<{ advisories: Advisory[]; data_source: DataSource }>('/advisories?status=active,accepted,rejected_by_whatif', 30_000)
  const [busy, setBusy] = useState(false)
  const [show, setShow] = useState<Kind | 'all'>('all')
  const act = async (id: number, action: 'accept' | 'dismiss') => { await postJSON(`/advisories/${id}/${action}`, {}); a.reload() }
  const runNow = async () => { setBusy(true); try { await postJSON('/advisories/run', {}) } finally { setBusy(false); a.reload() } }
  const all = (a.data?.advisories ?? []).map((x) => ({ ...x, kind: (x.kind ?? 'add_trips') as Kind }))
  const list = show === 'all' ? all : all.filter((x) => x.kind === show)
  const counts = all.reduce<Record<string, number>>((m, x) => ({ ...m, [x.kind]: (m[x.kind] ?? 0) + 1 }), {})
  return (
    <Panel title="Recommendations" right={
      <div className="flex items-center gap-2"><SimBadge source={a.data?.data_source} />
        <button className="btn-ghost text-sm" disabled={busy} onClick={runNow}>{busy ? 'Testing in twin…' : 'Read heatmap now'}</button></div>}>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Read from the heatmap every 15 minutes: two or more crowded slots in a row trigger extra trips (checked in the twin);
        crowding on the first part of a route suggests a short-turn; a quiet route nearby can lend a bus; a bus that fills up at a
        metro or MRTS station can wait for the train.
      </p>
      {all.length ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Show recommendations">
          {(['all', 'add_trips', 'short_turn', 'move_bus', 'hold_for_train'] as const).map((k) => (
            <button key={k} type="button" aria-pressed={show === k} onClick={() => setShow(k)}
              className={`tap rounded-full px-3 text-sm ring-1 ${show === k ? 'bg-brand text-white ring-brand' : 'ring-slate-300 dark:ring-slate-700'}`}
              disabled={k !== 'all' && !counts[k]}>
              {k === 'all' ? `All (${all.length})` : `${KIND[k].icon} ${KIND[k].label} (${counts[k] ?? 0})`}
            </button>
          ))}
        </div>
      ) : null}
      {!list.length ? <p className="text-sm text-slate-600 dark:text-slate-400">{a.loading ? 'Loading…' : 'Nothing to recommend for the next 3 hours.'}</p> : null}
      <ul className="grid gap-3 md:grid-cols-2">
        {list.map((x) => {
          const k = KIND[x.kind]
          return (
            <li key={x.advisory_id} className={`space-y-1.5 rounded-xl p-3 ring-1 ${x.status === 'accepted' ? 'ring-2 ring-teal-600' : x.status === 'rejected_by_whatif' ? 'ring-slate-300 opacity-70 dark:ring-slate-700' : 'ring-amber-400'}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold dark:bg-slate-800">{k.icon} {k.label}</span>
                  <b>{x.route} · {x.depot} depot</b>
                </span>
                <span className="text-xs uppercase text-slate-600 dark:text-slate-400">{x.status === 'rejected_by_whatif' ? 'did not pass twin test' : x.status}</span>
              </div>
              <p className="text-sm"><span className="font-medium">Why: </span>{x.reason} <span className="tabular-nums text-slate-600 dark:text-slate-400">({hhmm(x.slot_start)}–{hhmm(x.slot_end)})</span></p>
              <p className="font-semibold">➜ {x.action}</p>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {x.expected_lf_before != null ? <LevelChip level={levelOf(x.expected_lf_before)} lf={x.expected_lf_before} size="md" /> : null}
                {x.expected_lf_after != null ? <>→ <LevelChip level={levelOf(x.expected_lf_after)} lf={x.expected_lf_after} size="md" /></> : null}
                {x.kind === 'move_bus' && x.neighbour_lf_after != null ? <span className="text-xs text-slate-600 dark:text-slate-400">quiet route after: ≤ {Math.round(x.neighbour_lf_after * 100)}%</span> : null}
                {x.kind === 'add_trips' && x.neighbour_lf_after != null ? <span className="text-xs text-slate-600 dark:text-slate-400">neighbours ≤ {Math.round(x.neighbour_lf_after * 100)}%</span> : null}
                <span className="text-xs text-slate-600 dark:text-slate-400">· {x.extra_vehicle_hours ? `+${x.extra_vehicle_hours} bus-hours` : 'no extra bus-hours'}</span>
              </div>
              <p className="text-xs text-slate-600 dark:text-slate-400">{k.check}</p>
              {x.status === 'active' ? (
                <div className="flex gap-2 pt-1">
                  <button className="btn-primary text-sm" onClick={() => act(x.advisory_id, 'accept')}>Accept</button>
                  <button className="btn-ghost text-sm" onClick={() => act(x.advisory_id, 'dismiss')}>Dismiss</button>
                </div>
              ) : null}
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}
