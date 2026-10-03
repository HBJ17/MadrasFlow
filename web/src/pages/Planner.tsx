import { useEffect, useState } from 'react'
import { getJSON, hhmm, postJSON, usePolling, type PlanFilters, type RankKey, type StopInfo, type WindowPlan } from '../api'
import { LevelChip, SimBadge } from '../components'
import { useT } from '../i18n'
import { useLocation } from '../router'
import LocationField, { type Origin } from './planner/LocationField'
import RankToggles, { DEFAULT_RANK } from './planner/RankToggles'
import StopPicker from './planner/StopPicker'
import WindowStepper from './planner/WindowStepper'

export const DEFAULT_FILTERS: PlanFilters = { modes: ['bus', 'mrts', 'metro'], max_walk_min: null, max_fare: null, max_transfers: null, step_free: false, women: false }

const pad = (n: number) => String(n).padStart(2, '0')

export default function Planner() {
  const t = useT()
  const { params } = useLocation()
  const stops = usePolling<StopInfo[]>('/stops', 3600_000)
  const list = stops.data ?? []
  const initFrom = list.find((s) => s.stop_id === params.get('from')) ?? null
  const [origin, setOrigin] = useState<Origin | null>(null)
  const [to, setTo] = useState<StopInfo | null>(null)
  const [day, setDay] = useState<string | null>(null)       // service date from the server's (demo) clock
  const [time, setTime] = useState('')
  const [win, setWin] = useState(15)
  const [rank, setRank] = useState<RankKey[]>(DEFAULT_RANK)
  const [filters] = useState<PlanFilters>(DEFAULT_FILTERS)
  const [res, setRes] = useState<WindowPlan | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getJSON<{ now: string }>('/health').then(({ data }) => {
      const n = new Date(data.now)
      const ist = new Date(n.getTime() + (330 + n.getTimezoneOffset()) * 60000)
      setDay(`${ist.getFullYear()}-${pad(ist.getMonth() + 1)}-${pad(ist.getDate())}`)
      setTime((cur) => cur || `${pad(ist.getHours())}:${pad(ist.getMinutes())}`)
    }).catch(() => setTime((cur) => cur || `${pad(new Date().getHours())}:${pad(new Date().getMinutes())}`))
  }, [])

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!origin || !to) { setErr(t('pickStops')); return }
    setBusy(true); setErr(null)
    try {
      const depart_at = day && time ? `${day}T${time}:00+05:30` : null
      const { data } = await postJSON<WindowPlan>('/plan/window', {
        from_stop: origin.stop_id, to_stop: to.stop_id, depart_at, window_min: win,
        filters: { ...filters, access_walk_min: origin.walk_min }, rank_by: rank,
      })
      setRes(data)
    } catch (x) { setErr(String((x as Error).message)) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <button className="tap text-sm text-brand underline-offset-4 hover:underline dark:text-teal-300" onClick={() => history.back()}>← {t('back')}</button>
      <h1 className="text-2xl font-bold">{t('planTrip')}</h1>
      <form onSubmit={submit} className="card space-y-4 p-4">
        {list.length ? (
          <>
            <LocationField key={`f-${initFrom?.stop_id}`} stops={list} initialStop={initFrom} onChange={setOrigin} />
            <StopPicker id="to" label={t('to')} stops={list} value={to} onChange={setTo} />
          </>
        ) : <p className="text-sm text-slate-600 dark:text-slate-400">{t('loading')}</p>}
        <WindowStepper time={time} onTime={setTime} window={win} onWindow={setWin} />
        <RankToggles value={rank} onChange={setRank} />
        <button className="btn-primary w-full" disabled={busy}>{busy ? t('loading') : t('go')}</button>
        {err ? <p role="alert" className="text-sm text-red-700 dark:text-red-400">{err}</p> : null}
      </form>
      {res ? (
        <section className="space-y-3" aria-live="polite">
          <SimBadge source={res.data_source} />
          {res.slots.map((s) => (
            <div key={s.depart_at} className="card p-3">
              <h2 className="font-semibold">{t('leave')} {hhmm(s.depart_at)}</h2>
              {s.itineraries.length ? (
                <ul className="mt-2 space-y-1 text-sm">
                  {s.itineraries.map((it, i) => (
                    <li key={i} className="flex items-center justify-between gap-2">
                      <span>{it.rank}. {it.legs.filter((l) => l.kind === 'ride').map((l) => l.route).join(' → ')} · {t('arrive')} {hhmm(it.arrive_at)}</span>
                      <LevelChip level={it.worst_level} size="sm" />
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-slate-600 dark:text-slate-400">{t('noRoutesSlot')}</p>}
            </div>
          ))}
        </section>
      ) : null}
    </div>
  )
}
