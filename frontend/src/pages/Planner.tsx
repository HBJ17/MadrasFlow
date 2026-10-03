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

// Starred start/end pairs, kept on this device.
const STARS = 'mf-starred-trips'
interface Star { from: string; from_name: string; to: string; to_name: string }
function loadStars(): Star[] {
  try { return JSON.parse(localStorage.getItem(STARS) || '[]') } catch { return [] }
}

export default function Planner() {
  const t = useT()
  const { path, params } = useLocation()
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
  const [stars, setStars] = useState<Star[]>(loadStars)
  const [preset, setPreset] = useState<{ from: StopInfo; to: StopInfo; n: number } | null>(null)   // a starred trip loaded into the form
  useEffect(() => { try { localStorage.setItem(STARS, JSON.stringify(stars)) } catch { /* storage may be unavailable */ } }, [stars])
  const starred = !!origin && !!to && stars.some((x) => x.from === origin.stop_id && x.to === to.stop_id)
  const toggleStar = () => {
    if (!origin || !to) return
    setStars(starred ? stars.filter((x) => !(x.from === origin.stop_id && x.to === to.stop_id))
      : [{ from: origin.stop_id, from_name: origin.name, to: to.stop_id, to_name: to.name }, ...stars])
  }

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

  const submit = async (e?: React.FormEvent, origin_ = origin, to_ = to) => {
    e?.preventDefault()
    const origin = origin_, to = to_
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

  // Load a starred trip into the form and search it straight away.
  const loadStar = (x: Star) => {
    const f = list.find((s) => s.stop_id === x.from), d = list.find((s) => s.stop_id === x.to)
    if (!f || !d) return
    const o: Origin = { stop_id: f.stop_id, name: f.name, walk_min: 0, gps: false }
    setPreset({ from: f, to: d, n: (preset?.n ?? 0) + 1 })
    setOrigin(o); setTo(d)
    submit(undefined, o, d)
  }

  return (
    <div className="space-y-4">
      {path === '/plan' ? <BackButton label={t('back')} /> : null}
      <div className="space-y-1 pt-1">
        <p className="font-display text-[40px] font-bold leading-[1.05] tracking-[-0.03em] text-[#002046] sm:text-5xl dark:text-navy-soft">{t('hello')}</p>
        <h1 className="ledger text-xs">{t('planTrip')}</h1>
      </div>
      <form onSubmit={submit} className="card space-y-4 p-4">
        {list.length ? (
          <>
            <LocationField key={preset ? `p-${preset.n}` : `f-${initFrom?.stop_id}`} stops={list} initialStop={preset?.from ?? initFrom} onChange={setOrigin} />
            <StopPicker key={`to-${preset?.n ?? 0}`} id="to" label={t('to')} stops={list} value={to} onChange={setTo} />
          </>
        ) : <p className="ledger">{t('loading')}</p>}
        <WindowStepper time={time} onTime={setTime} window={win} onWindow={setWin} />
        <RankToggles value={rank} onChange={setRank} />
        <div className="flex gap-3 border-t border-slate-200 pt-4 dark:border-white/5">
          <button type="button" className="btn-ghost" onClick={() => setSheet(true)} aria-haspopup="dialog">
            <Icon name="tune" className="h-4 w-4" /> {t('filters')}{activeFilterCount(filters) ? <span className="rounded-md bg-lime px-1.5 font-mono text-xs font-bold text-lime-ink">{activeFilterCount(filters)}</span> : null}
          </button>
          <button type="button" className={`btn-ghost w-11 shrink-0 px-0 ${starred ? 'text-amber-700 dark:text-amber-300' : ''}`} onClick={toggleStar}
            disabled={!origin || !to} aria-pressed={starred} aria-label={starred ? t('unstarTrip') : t('starTrip')} title={starred ? t('unstarTrip') : t('starTrip')}>
            <Icon name={starred ? 'star' : 'starOutline'} className="h-5 w-5" />
          </button>
          <button className="btn-primary flex-1" disabled={busy}>{busy ? t('loading') : t('go')}</button>
        </div>
        {err ? <p role="alert" className="text-sm text-red-700 dark:text-red-400">{err}</p> : null}
      </form>
      <section aria-labelledby="stars-h" className="space-y-2">
        <h2 id="stars-h" className="ledger flex items-center gap-1.5"><Icon name="star" className="h-3.5 w-3.5 text-amber-700 dark:text-amber-300" />{t('starred')}</h2>
        {stars.length ? (
          <ul className="card divide-y divide-slate-200 overflow-hidden dark:divide-white/5">
            {stars.map((x) => (
              <li key={`${x.from}|${x.to}`} className="flex items-center">
                <button type="button" onClick={() => loadStar(x)} className="tap flex min-w-0 flex-1 items-center gap-2 px-4 py-2.5 text-left transition hover:bg-slate-100 dark:hover:bg-[#1f232d]">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-display font-semibold text-[#002046] dark:text-navy-soft">{x.from_name}</span>
                    <span className="block truncate text-sm text-slate-600 dark:text-slate-300">→ {x.to_name}</span>
                  </span>
                  <span aria-hidden className="text-slate-500">›</span>
                </button>
                <button type="button" className="tap mr-1 flex items-center justify-center rounded-full text-amber-700 hover:bg-slate-100 dark:text-amber-300 dark:hover:bg-white/5"
                  aria-label={`${t('unstarTrip')}: ${x.from_name} → ${x.to_name}`} title={t('unstarTrip')}
                  onClick={() => setStars(stars.filter((y) => y !== x))}>
                  <Icon name="star" className="h-5 w-5" />
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="rounded-xl border border-dashed border-slate-300 px-4 py-3 text-sm text-slate-600 dark:border-white/10 dark:text-slate-400">{t('starHint')}</p>}
      </section>
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
