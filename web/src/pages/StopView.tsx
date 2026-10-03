import { usePolling, type StopOccupancy, type WaitOrGo } from '../api'
import { BackButton, Icon, LevelChip, ModeIcon, ModeTile, SimBadge, Spinner, StaleBanner } from '../components'
import { useT } from '../i18n'
import { Link } from '../router'
import { useFavourites } from './Home'

function WaitHint({ stopId, routeId, direction }: { stopId: string; routeId: string; direction: number }) {
  const w = usePolling<WaitOrGo>(`/wait-or-go?stop_id=${encodeURIComponent(stopId)}&route_id=${routeId}&direction=${direction}`)
  if (!w.data) return null
  return <p className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200"><Icon name="bulb" className="mt-0.5 h-4 w-4 text-amber-700 dark:text-amber-300" /> <span>{w.data.suggestion}</span></p>
}

export default function StopView({ stopId }: { stopId: string }) {
  const t = useT()
  const occ = usePolling<StopOccupancy>(`/occupancy/stop/${encodeURIComponent(stopId)}?n=5`)
  const { fav, toggle } = useFavourites()
  const d = occ.data
  const groups = new Map<string, { route_id: string; route: string; direction: number; to: string; mode: string }>()
  d?.vehicles.forEach((v) => groups.set(`${v.route_id}|${v.direction}`, v))
  const saved = fav.includes(stopId)

  return (
    <div className="space-y-4">
      <BackButton label={t('back')} />
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[28px] font-bold leading-tight text-[#002046] dark:text-navy-soft">{d?.name ?? stopId}</h1>
        <button className={`btn-ghost text-sm ${saved ? 'text-amber-700 dark:text-amber-300' : ''}`} aria-pressed={saved} onClick={() => toggle(stopId)}>
          <Icon name={saved ? 'star' : 'starOutline'} className="h-4 w-4" /> {saved ? t('saved') : t('save')}
        </button>
        <SimBadge source={d?.data_source} />
      </div>
      <StaleBanner since={occ.staleSince} error={!d ? occ.error : null} onRetry={occ.reload} />
      {occ.loading && !d ? <Spinner /> : null}

      <section className="space-y-2" aria-labelledby="up-h">
        <h2 id="up-h" className="ledger">{t('upcoming')}</h2>
        <ul className="card divide-y divide-slate-200 overflow-hidden dark:divide-white/5">
          {d?.vehicles.map((v) => (
            <li key={v.trip_id}>
              <Link to={`/vehicle/${encodeURIComponent(v.vehicle_id)}`} className="tap flex items-center gap-3 px-3 py-3 transition hover:bg-slate-100 dark:hover:bg-[#1f232d]">
                <ModeTile mode={v.mode} small />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="font-display font-bold text-[#002046] dark:text-navy-soft">{v.route}</span>
                  <span className="truncate text-sm text-slate-600 dark:text-slate-300">→ {v.to}</span>
                </span>
                <span className="flex flex-col items-end gap-1">
                  <span className="flex items-baseline gap-0.5 rounded-lg bg-slate-200 px-2 py-0.5 text-ink dark:bg-[#252b36] dark:text-slate-100">
                    <span className="font-display text-lg font-bold leading-none tabular-nums">{v.eta_min}</span>
                    <span className="font-mono text-[10px] font-bold uppercase">{t('min')}</span>
                  </span>
                  <LevelChip level={v.level} lf={v.load_factor} size="sm" />
                </span>
              </Link>
            </li>
          ))}
          {d && d.vehicles.length === 0 ? <li className="px-4 py-3 text-sm text-slate-600 dark:text-slate-400">—</li> : null}
        </ul>
      </section>

      {groups.size > 0 ? (
        <section className="space-y-2" aria-labelledby="wog-h">
          <h2 id="wog-h" className="ledger">{t('waitOrGo')}</h2>
          {[...groups.values()].map((g) => (
            <div key={g.route_id + g.direction} className="card space-y-1 px-4 py-3">
              <Link to={`/route/${g.route_id}?d=${g.direction}`} className="inline-flex items-center gap-1.5 font-display font-semibold text-[#002046] underline-offset-4 hover:underline dark:text-navy-soft">
                <ModeIcon mode={g.mode} /> {g.route} → {g.to}
              </Link>
              <WaitHint stopId={stopId} routeId={g.route_id} direction={g.direction} />
            </div>
          ))}
        </section>
      ) : null}
      <Link to={`/plan?from=${encodeURIComponent(stopId)}`} className="btn-primary h-12 w-full"><Icon name="explore" className="h-5 w-5 text-lime dark:text-[#002046]" /> {t('planTrip')}</Link>
    </div>
  )
}
