import { useMemo, useState } from 'react'
import { hhmm, postJSON, usePolling, type Itinerary, type Plan, type StopInfo } from '../api'
import { LevelChip, ModeIcon, SimBadge } from '../components'
import { useT } from '../i18n'
import { useLocation } from '../router'

function StopPicker({ id, label, stops, value, onChange }: {
  id: string; label: string; stops: StopInfo[]; value: StopInfo | null; onChange: (s: StopInfo | null) => void
}) {
  const [q, setQ] = useState(value?.name ?? '')
  const [open, setOpen] = useState(false)
  const opts = useMemo(() => {
    const s = q.toLowerCase()
    const seen = new Set<string>()
    return stops.filter((x) => x.name.toLowerCase().includes(s) && !seen.has(x.station_id) && seen.add(x.station_id)).slice(0, 8)
  }, [q, stops])
  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-sm font-medium">{label}</label>
      <input id={id} className="input" value={q} autoComplete="off" role="combobox" aria-expanded={open} aria-controls={`${id}-list`}
        onChange={(e) => { setQ(e.target.value); setOpen(true); onChange(null) }} onFocus={() => setOpen(true)} />
      {open && q && opts.length > 0 ? (
        <ul id={`${id}-list`} role="listbox" className="card absolute z-10 mt-1 w-full overflow-hidden">
          {opts.map((s) => (
            <li key={s.stop_id} role="option" aria-selected={value?.stop_id === s.stop_id}>
              <button type="button" className="tap flex w-full items-center gap-2 px-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800"
                onClick={() => { onChange(s); setQ(s.name); setOpen(false) }}>
                <ModeIcon mode={s.mode} /> {s.name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

function ItineraryCard({ it }: { it: Itinerary }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const label = it.labels.map((l) => t(l as 'fastest')).join(' · ')
  const rides = it.legs.filter((l) => l.kind === 'ride')
  return (
    <li className="card overflow-hidden">
      <button className="tap w-full px-4 py-3 text-left" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold uppercase tracking-wide text-brand dark:text-teal-300">{label}</span>
          <LevelChip level={it.worst_level} size="sm" />
        </div>
        <div className="mt-1 flex items-baseline gap-3">
          <span className="text-2xl font-bold tabular-nums">{Math.round(it.total_min)} {t('min')}</span>
          <span className="text-sm text-slate-600 dark:text-slate-300">
            {t('arrive')} {hhmm(it.arrive_at)} · {it.transfers} {it.transfers === 1 ? t('transfer') : t('transfers')}
          </span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1 text-sm">
          {rides.map((l, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 ? <span aria-hidden>›</span> : null}
              <ModeIcon mode={l.mode!} /> <b>{l.route}</b>
            </span>
          ))}
        </div>
      </button>
      {open ? (
        <ol className="space-y-3 border-t border-slate-100 px-4 py-3 dark:border-slate-800">
          {it.legs.map((l, i) => l.kind === 'walk' ? (
            <li key={i} className="text-sm text-slate-600 dark:text-slate-300">🚶 {t('walk')} {Math.round(l.minutes)} {t('min')}: {l.from} → {l.to}</li>
          ) : (
            <li key={i} className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span><ModeIcon mode={l.mode!} /> <b>{l.route}</b> · {l.stops} {t('stops')} · {Math.round(l.minutes)} {t('min')}</span>
                <LevelChip level={l.level} size="sm" />
              </div>
              <div className="text-sm text-slate-600 dark:text-slate-300">
                {t('board')} {l.from} {hhmm(l.board_at!)} {l.wait_min ? `(+${Math.round(l.wait_min)}′)` : ''} → {t('alight')} {l.to} {hhmm(l.alight_at!)}
              </div>
              <div className="flex h-2 gap-px overflow-hidden rounded" aria-hidden>
                {l.levels!.map((lv, j) => <span key={j} className={`bar-${lv} flex-1`} />)}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </li>
  )
}

export default function Planner() {
  const t = useT()
  const { params } = useLocation()
  const stops = usePolling<StopInfo[]>('/stops', 3600_000)
  const list = stops.data ?? []
  const initFrom = list.find((s) => s.stop_id === params.get('from')) ?? null
  const [from, setFrom] = useState<StopInfo | null>(null)
  const [to, setTo] = useState<StopInfo | null>(null)
  const [when, setWhen] = useState('')
  const [low, setLow] = useState(false)
  const [res, setRes] = useState<Plan | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const f = from ?? initFrom

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!f || !to) { setErr('Pick both stops from the list'); return }
    setBusy(true); setErr(null)
    try {
      let depart_at: string | null = null
      if (when) { const d = new Date(); const [h, m] = when.split(':').map(Number); d.setHours(h, m, 0, 0); depart_at = d.toISOString() }
      const { data } = await postJSON<Plan>('/plan', { from_stop: f.stop_id, to_stop: to.stop_id, depart_at, prefer_low_crowd: low })
      setRes(data)
    } catch (x) { setErr(String((x as Error).message)) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <button className="tap text-sm text-brand underline-offset-4 hover:underline dark:text-teal-300" onClick={() => history.back()}>← {t('back')}</button>
      <h1 className="text-2xl font-bold">{t('planTrip')}</h1>
      <form onSubmit={submit} className="card space-y-3 p-4">
        {list.length ? (
          <>
            <StopPicker key={`f-${initFrom?.stop_id}`} id="from" label={t('from')} stops={list} value={f} onChange={setFrom} />
            <StopPicker id="to" label={t('to')} stops={list} value={to} onChange={setTo} />
          </>
        ) : <p className="text-sm text-slate-600 dark:text-slate-400">{t('loading')}</p>}
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="when" className="mb-1 block text-sm font-medium">{t('departAt')}</label>
            <input id="when" type="time" className="input w-36" value={when} onChange={(e) => setWhen(e.target.value)} />
          </div>
          {when ? <button type="button" className="btn-ghost text-sm" onClick={() => setWhen('')}>{t('departNow')}</button> : <span className="pb-3 text-sm text-slate-600 dark:text-slate-400">{t('departNow')}</span>}
        </div>
        <label className="tap flex cursor-pointer items-center gap-3">
          <input type="checkbox" className="h-6 w-6 accent-teal-700" checked={low} onChange={(e) => setLow(e.target.checked)} />
          <span>
            <span className="font-medium">{t('preferLow')}</span>
            <span className="block text-xs text-slate-600 dark:text-slate-400">{t('preferLowHint')}</span>
          </span>
        </label>
        <button className="btn-primary w-full" disabled={busy}>{busy ? t('loading') : t('go')}</button>
        {err ? <p role="alert" className="text-sm text-red-700 dark:text-red-400">{err}</p> : null}
      </form>
      {res ? (
        <section className="space-y-3" aria-live="polite">
          <div className="flex items-center gap-2"><SimBadge source={res.data_source} /></div>
          {res.itineraries.length === 0 ? <p>{res.message}</p> : null}
          <ul className="space-y-3">{res.itineraries.map((it, i) => <ItineraryCard key={i} it={it} />)}</ul>
        </section>
      ) : null}
    </div>
  )
}
