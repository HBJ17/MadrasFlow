import { useEffect, useRef, useState } from 'react'
import { getJSON, postJSON, usePolling, type PlanFilters, type RankKey, type StopInfo, type WindowPlan } from '../api'
import { BackButton, Icon, SimBadge } from '../components'
import { useT } from '../i18n'
import { useLocation } from '../router'
import FilterSheet, { activeFilterCount } from './planner/FilterSheet'
import LocationField, { type Origin } from './planner/LocationField'
import RankToggles, { DEFAULT_RANK } from './planner/RankToggles'
import RouteDetail from './planner/RouteDetail'
import SlotCarousel, { type Selection } from './planner/SlotCarousel'
import StopPicker from './planner/StopPicker'
import WindowStepper from './planner/WindowStepper'

export const DEFAULT_FILTERS: PlanFilters = { modes: ['bus', 'mrts', 'metro'], max_walk_min: null, max_fare: null, max_transfers: null, step_free: false, women: false }

const pad = (n: number) => String(n).padStart(2, '0')
const PREFS = 'mf-planner'
interface Prefs { win: number; rank: RankKey[]; filters: PlanFilters }
function loadPrefs(): Partial<Prefs> {
  try { return JSON.parse(localStorage.getItem(PREFS) || '{}') } catch { return {} }
}

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
  const prefs = useRef(loadPrefs()).current
  const [win, setWin] = useState(prefs.win ?? 15)
  const [rank, setRank] = useState<RankKey[]>(prefs.rank ?? DEFAULT_RANK)
  const [filters, setFilters] = useState<PlanFilters>({ ...DEFAULT_FILTERS, ...prefs.filters })
  const [sheet, setSheet] = useState(false)
  const [res, setRes] = useState<WindowPlan | null>(null)
  const [sel, setSel] = useState<Selection | null>(null)
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

  // remember choices on this device; once results are shown, re-plan when a choice changes
  useEffect(() => {
    try { localStorage.setItem(PREFS, JSON.stringify({ win, rank, filters })) } catch { /* storage may be unavailable */ }
    if (!res) return
    const h = window.setTimeout(() => submit(), 300)
    return () => window.clearTimeout(h)
  }, [win, rank, filters]) // eslint-disable-line react-hooks/exhaustive-deps

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
      setSel(null)
    } catch (x) { setErr(String((x as Error).message)) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <BackButton label={t('back')} />
      <h1 className="text-[28px] font-bold leading-tight text-[#002046] dark:text-navy-soft">{t('planTrip')}</h1>
      <form onSubmit={submit} className="card space-y-4 p-4">
        {list.length ? (
          <>
            <LocationField key={`f-${initFrom?.stop_id}`} stops={list} initialStop={initFrom} onChange={setOrigin} />
            <StopPicker id="to" label={t('to')} stops={list} value={to} onChange={setTo} />
          </>
        ) : <p className="ledger">{t('loading')}</p>}
        <WindowStepper time={time} onTime={setTime} window={win} onWindow={setWin} />
        <RankToggles value={rank} onChange={setRank} />
        <div className="flex gap-3 border-t border-slate-200 pt-4 dark:border-white/5">
          <button type="button" className="btn-ghost" onClick={() => setSheet(true)} aria-haspopup="dialog">
            <Icon name="tune" className="h-4 w-4" /> {t('filters')}{activeFilterCount(filters) ? <span className="rounded-md bg-lime px-1.5 font-mono text-xs font-bold text-lime-ink">{activeFilterCount(filters)}</span> : null}
          </button>
          <button className="btn-primary flex-1" disabled={busy}>{busy ? t('loading') : t('go')}</button>
        </div>
        {err ? <p role="alert" className="text-sm text-red-700 dark:text-red-400">{err}</p> : null}
      </form>
      <FilterSheet open={sheet} value={filters} defaults={DEFAULT_FILTERS} onClose={() => setSheet(false)} onApply={setFilters} />
      {res ? (
        <section className="space-y-3" aria-live="polite">
          <div className="flex items-center gap-3">
            <SimBadge source={res.data_source} />
            {busy ? <span role="status" className="ledger">{t('updating')}</span> : null}
          </div>
          <SlotCarousel plan={res} selected={sel} onSelect={setSel} />
          {sel && res.slots[sel.slot]?.itineraries[sel.idx] ? (
            <RouteDetail it={res.slots[sel.slot].itineraries[sel.idx]} departAt={res.slots[sel.slot].depart_at} />
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
