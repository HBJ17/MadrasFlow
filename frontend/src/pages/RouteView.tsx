import { Suspense, useState } from 'react'
import { lazyReload } from '../lazyReload'
import { hhmm, levelOf, pct, usePolling, type RouteInfo, type RouteOccupancy } from '../api'
import { BackButton, Icon, LevelChip, LoadBar, ModeTile, SimBadge, Spinner, StaleBanner } from '../components'
import { useT } from '../i18n'
import { Link, navigate, useLocation } from '../router'

const MapView = lazyReload(() => import('./MapView'))

// Strip offset: 0 = next vehicle at each stop; 2 / 4 slots ahead = in 30 min / 1 h.
const OFFSETS = [
  { key: 'now', slots: 0 },
  { key: 'in30', slots: 2 },
  { key: 'in60', slots: 4 },
] as const

export default function RouteView({ routeId }: { routeId: string }) {
  const t = useT()
  const { params } = useLocation()
  const dir = Number(params.get('d') || 0)
  const [off, setOff] = useState<(typeof OFFSETS)[number]['key']>('now')
  const [map, setMap] = useState(false)
  const routes = usePolling<RouteInfo[]>('/routes', 3600_000)
  const occ = usePolling<RouteOccupancy>(`/occupancy/route/${encodeURIComponent(routeId)}?direction=${dir}`)
  const info = routes.data?.find((r) => r.route_id === routeId)
  const dirs = info?.directions ?? []
  const slots = OFFSETS.find((o) => o.key === off)!.slots
  const d = occ.data

  return (
    <div className="space-y-4">
      <BackButton label={t('back')} />
      <div className="flex flex-wrap items-center gap-3">
        <ModeTile mode={info?.mode ?? 'bus'} />
        <h1 className="text-[28px] font-bold leading-tight text-[#002046] dark:text-navy-soft">{info?.short_name ?? routeId}</h1>
        <span className="text-slate-600 dark:text-slate-300">{info?.long_name}</span>
        <SimBadge source={d?.data_source} />
      </div>

      <div className="flex gap-1.5 rounded-xl bg-slate-100 p-1 dark:bg-[#1a1d25]" role="group" aria-label={t('direction')}>
        {dirs.map((x) => (
          <button key={x.direction} className="seg" aria-pressed={x.direction === dir}
            onClick={() => navigate(`/route/${routeId}?d=${x.direction}`)}>
            → {x.to}
          </button>
        ))}
      </div>
      <div className="flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-[#1a1d25]" role="group" aria-label="time">
        {OFFSETS.map((o) => (
          <button key={o.key} className="seg font-mono text-xs uppercase tracking-wide" aria-pressed={off === o.key} onClick={() => setOff(o.key)}>{t(o.key)}</button>
        ))}
      </div>

      <button className="btn-ghost w-full" onClick={() => setMap((m) => !m)}><Icon name="map" className="h-4 w-4" /> {map ? t('hideMap') : t('showMap')}</button>
      {map && d ? (
        <Suspense fallback={<Spinner />}>
          <MapView stops={d.stops.map((s) => ({ id: s.stop_id, name: s.name, level: s.level }))} />
        </Suspense>
      ) : null}
      <StaleBanner since={occ.staleSince} error={!d ? occ.error : null} onRetry={occ.reload} />
      {occ.loading && !d ? <Spinner /> : null}
      {d && !d.made_at ? <p className="text-sm text-slate-600 dark:text-slate-400">{t('noData')}</p> : null}

      {d ? (
        <ol className="card divide-y divide-slate-200 dark:divide-white/5" aria-label="crowd strip">
          {d.stops.map((s, i) => {
            const fv = slots === 0 ? null : s.f[slots] ?? null
            const lf = slots === 0 ? s.load_factor : fv?.[0] ?? null
            const lvl = slots === 0 ? s.level : levelOf(lf)
            const last = i === d.stops.length - 1
            return (
              <li key={s.stop_id + s.seq} className="flex items-center gap-3 px-3 py-2">
                <span className={`bar-${last ? 'none' : lvl ?? 'LOW'} h-3 w-3 shrink-0 rounded-full ring-2 ring-card`} aria-hidden />
                <Link to={`/stop/${encodeURIComponent(s.stop_id)}`} className="tap flex min-w-0 flex-1 flex-col justify-center">
                  <span className="font-display text-sm font-semibold leading-snug text-[#002046] dark:text-navy-soft">{s.name}</span>
                  {last ? null : (
                    <span className="mt-1 flex items-center gap-2">
                      <span className="flex-1"><LoadBar lf={lf} /></span>
                      <span className="w-14 text-right font-mono text-[11px] tabular-nums text-slate-600 dark:text-slate-300">
                        {s.eta_min != null && slots === 0 ? `${t('nextVehicle')} ${s.eta_min}′` : ''}
                      </span>
                    </span>
                  )}
                </Link>
                {last ? null : (
                  <span className="flex w-20 shrink-0 flex-col items-end gap-0.5">
                    <LevelChip level={lvl} lf={lf} size="sm" />
                    <span className="font-mono text-[11px] font-semibold tabular-nums text-slate-600 dark:text-slate-300">{pct(lf)}</span>
                  </span>
                )}
              </li>
            )
          })}
        </ol>
      ) : null}
      {d?.made_at ? (
        <p className="font-mono text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
          Forecast {hhmm(d.made_at)} · {d.model} · load % = people on board + people left waiting, ÷ capacity incl. standing.
          {d.stops.some((s) => s.stale) ? ` ${t('stale')}.` : ''}
        </p>
      ) : null}

    </div>
  )
}
