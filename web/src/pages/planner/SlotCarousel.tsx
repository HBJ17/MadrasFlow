// One card per departure slot (08:15 / 08:30 / 08:45 ...). Swipe or use the arrows to move between
// slots; scroll down inside a card to see all ranked routes for that slot. Crowd is shown as a level
// only (Low / Medium / High / Crowded).
import { useEffect, useRef, useState } from 'react'
import { hhmm, type WinItinerary, type WindowPlan } from '../../api'
import { LevelChip, ModeIcon } from '../../components'
import { useT } from '../../i18n'

export interface Selection { slot: number; idx: number }

function RouteOption({ it, selected, onSelect }: { it: WinItinerary; selected: boolean; onSelect: () => void }) {
  const t = useT()
  const rides = it.legs.filter((l) => l.kind === 'ride')
  const notes = it.notes.map((n) => (n.startsWith('low_floor_not_guaranteed') ? 'low_floor' : n === 'after_dark_short_walks_waits' ? 'after_dark' : n))
  return (
    <li>
      <button type="button" aria-pressed={selected} onClick={onSelect}
        className={`w-full rounded-xl px-3 py-3 text-left ring-1 transition ${selected ? 'bg-teal-50 ring-2 ring-brand dark:bg-teal-950/40' : 'ring-slate-200 hover:bg-slate-50 dark:ring-slate-800 dark:hover:bg-slate-800/60'}`}>
        <div className="flex items-start justify-between gap-2">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-slate-200 text-xs font-bold tabular-nums dark:bg-slate-700">{it.rank}</span>
            {rides.map((l, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 ? <span aria-hidden className="text-slate-500">›</span> : null}
                <ModeIcon mode={l.mode!} /><b>{l.route}</b>
              </span>
            ))}
          </span>
          <LevelChip level={it.worst_level} size="sm" />
        </div>
        <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-lg font-bold tabular-nums">{t('arrive')} {hhmm(it.arrive_at)}</span>
          <span className="text-sm tabular-nums text-slate-600 dark:text-slate-300">{Math.round(it.total_min)} {t('min')}</span>
          <span className="text-sm tabular-nums text-slate-600 dark:text-slate-300">₹{Math.round(it.fare)}</span>
          <span className="text-sm text-slate-600 dark:text-slate-300">
            {it.transfers} {it.transfers === 1 ? t('transfer') : t('transfers')}{it.walk_min >= 1 ? ` · ${t('walk')} ${Math.round(it.walk_min)} ${t('min')}` : ''}
          </span>
        </div>
        {it.best_overall || notes.length ? (
          <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
            {it.best_overall ? <span className="rounded-full bg-brand px-2 py-0.5 font-semibold text-white">★ {t('bestOverall')}</span> : null}
            {[...new Set(notes)].map((n) => <span key={n} className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-700 dark:bg-slate-800 dark:text-slate-300">{t(n as 'low_floor')}</span>)}
          </div>
        ) : null}
      </button>
    </li>
  )
}

export default function SlotCarousel({ plan, selected, onSelect }: { plan: WindowPlan; selected: Selection | null; onSelect: (s: Selection) => void }) {
  const t = useT()
  const track = useRef<HTMLDivElement>(null)
  const n = plan.slots.length
  const mid = Math.floor(n / 2)
  const [cur, setCur] = useState(mid)

  const go = (i: number, smooth = true) => {
    const el = track.current
    if (!el) return
    const k = Math.max(0, Math.min(n - 1, i))
    el.scrollTo({ left: k * el.clientWidth, behavior: smooth && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'auto' })
    setCur(k)
  }
  useEffect(() => { go(mid, false) }, [plan]) // eslint-disable-line react-hooks/exhaustive-deps
  const onScroll = () => {
    const el = track.current
    if (el && el.clientWidth) setCur(Math.round(el.scrollLeft / el.clientWidth))
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <button type="button" className="btn-ghost w-11 px-0" aria-label={t('prevSlot')} disabled={cur === 0} onClick={() => go(cur - 1)}>◀</button>
        <div role="tablist" aria-label={t('leave')} className="flex flex-1 gap-1 overflow-x-auto">
          {plan.slots.map((s, i) => (
            <button key={s.depart_at} role="tab" type="button" aria-selected={i === cur} onClick={() => go(i)}
              className={`tap shrink-0 rounded-lg px-3 text-sm font-semibold tabular-nums ${i === cur ? 'bg-brand text-white' : 'text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'}`}>
              {hhmm(s.depart_at)}
            </button>
          ))}
        </div>
        <button type="button" className="btn-ghost w-11 px-0" aria-label={t('nextSlot')} disabled={cur === n - 1} onClick={() => go(cur + 1)}>▶</button>
      </div>
      <div ref={track} onScroll={onScroll} className="flex snap-x snap-mandatory overflow-x-auto [scrollbar-width:none]">
        {plan.slots.map((s, si) => (
          <section key={s.depart_at} role="tabpanel" aria-label={`${t('leave')} ${hhmm(s.depart_at)}`} className="w-full shrink-0 snap-center px-0.5">
            <div className="card p-3">
              <div className="mb-2 flex items-baseline justify-between">
                <h2 className="text-lg font-semibold">{t('leave')} {hhmm(s.depart_at)}</h2>
                <span className="text-sm text-slate-600 dark:text-slate-400">{s.itineraries.length} {t('options')}</span>
              </div>
              {s.itineraries.length ? (
                <ul className="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
                  {s.itineraries.map((it, i) => (
                    <RouteOption key={i} it={it} selected={selected?.slot === si && selected.idx === i} onSelect={() => onSelect({ slot: si, idx: i })} />
                  ))}
                </ul>
              ) : <p className="py-6 text-center text-sm text-slate-600 dark:text-slate-400">{t('noRoutesSlot')}</p>}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
