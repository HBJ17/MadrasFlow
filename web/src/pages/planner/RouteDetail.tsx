// The chosen route: map (lazy) plus the step-by-step legs with times, waits, fares and crowd levels.
import { Suspense, useEffect, useRef } from 'react'
import { hhmm, type WinItinerary } from '../../api'
import { Icon, LevelChip, ModeTile, Spinner } from '../../components'
import { useT } from '../../i18n'
import { lazyReload } from '../../lazyReload'

const RouteMap = lazyReload(() => import('./RouteMap'))

export default function RouteDetail({ it, departAt }: { it: WinItinerary; departAt: string }) {
  const t = useT()
  const ref = useRef<HTMLElement>(null)
  useEffect(() => { ref.current?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }) }, [it])
  return (
    <section ref={ref} className="space-y-3 scroll-mt-16" aria-label={t('routeMap')}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="text-lg font-semibold text-[#002046] dark:text-navy-soft">{t('routeMap')}</h2>
        <span className="font-mono text-xs font-semibold tabular-nums text-slate-600 dark:text-slate-400">{t('leave')} {hhmm(departAt)} · {t('arrive')} {hhmm(it.arrive_at)} · ₹{Math.round(it.fare)}</span>
      </div>
      <Suspense fallback={<Spinner />}><RouteMap it={it} /></Suspense>
      <ol className="card divide-y divide-slate-200 px-4 dark:divide-white/5">
        {it.legs.map((l, i) => l.kind === 'walk' ? (
          <li key={i} className="flex items-center gap-2 py-2.5 text-sm text-slate-600 dark:text-slate-300"><Icon name="walk" className="h-4 w-4" /> {t('walk')} {Math.round(l.minutes)} {t('min')}: {l.from} → {l.to}</li>
        ) : (
          <li key={i} className="space-y-1.5 py-3">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2"><ModeTile mode={l.mode!} small /> <span><b className="font-display text-[#002046] dark:text-navy-soft">{l.route}</b> · {l.stops} {t('stops')} · {Math.round(l.minutes)} {t('min')}{l.fare != null ? ` · ₹${Math.round(l.fare)}` : ''}</span></span>
              <LevelChip level={l.level} size="sm" />
            </div>
            <div className="text-sm text-slate-600 dark:text-slate-300">
              {t('board')} {l.from} {hhmm(l.board_at!)}{l.wait_min ? ` (${Math.round(l.wait_min)} ${t('min')} ${t('wait')})` : ''} → {t('alight')} {l.to} {hhmm(l.alight_at!)}
            </div>
            <div className="flex h-2 gap-px overflow-hidden rounded-full" aria-hidden>
              {l.levels!.map((lv, j) => <span key={j} className={`bar-${lv} flex-1`} />)}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
