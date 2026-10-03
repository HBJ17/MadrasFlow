import { usePolling, type StopOccupancy, type WaitOrGo } from '../api'
import { LevelChip, ModeIcon, SimBadge, Spinner, StaleBanner } from '../components'
import { useT } from '../i18n'
import { Link } from '../router'
import { useFavourites } from './Home'

function WaitHint({ stopId, routeId, direction }: { stopId: string; routeId: string; direction: number }) {
  const w = usePolling<WaitOrGo>(`/wait-or-go?stop_id=${encodeURIComponent(stopId)}&route_id=${routeId}&direction=${direction}`)
  if (!w.data) return null
  return <p className="text-sm text-slate-700 dark:text-slate-200">💡 {w.data.suggestion}</p>
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
      <button className="tap text-sm text-brand underline-offset-4 hover:underline dark:text-teal-300" onClick={() => history.back()}>← {t('back')}</button>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{d?.name ?? stopId}</h1>
        <button className="btn-ghost text-sm" aria-pressed={saved} onClick={() => toggle(stopId)}>
          {saved ? '★ ' + t('saved') : '☆ ' + t('save')}
        </button>
        <SimBadge source={d?.data_source} />
      </div>
      <StaleBanner since={occ.staleSince} error={!d ? occ.error : null} onRetry={occ.reload} />
      {occ.loading && !d ? <Spinner /> : null}

      <section className="space-y-2" aria-labelledby="up-h">
        <h2 id="up-h" className="font-semibold">{t('upcoming')}</h2>
        <ul className="card divide-y divide-slate-100 dark:divide-slate-800">
          {d?.vehicles.map((v) => (
            <li key={v.trip_id}>
              <Link to={`/vehicle/${encodeURIComponent(v.vehicle_id)}`} className="tap flex items-center gap-3 px-4 py-3">
                <ModeIcon mode={v.mode} />
                <span className="w-12 font-bold">{v.route}</span>
                <span className="flex-1 truncate text-sm text-slate-600 dark:text-slate-300">→ {v.to}</span>
                <span className="w-14 text-right font-semibold tabular-nums">{v.eta_min}′</span>
                <span className="w-28 text-right"><LevelChip level={v.level} lf={v.load_factor} size="sm" /></span>
              </Link>
            </li>
          ))}
          {d && d.vehicles.length === 0 ? <li className="px-4 py-3 text-sm text-slate-600 dark:text-slate-400">—</li> : null}
        </ul>
      </section>

      {groups.size > 0 ? (
        <section className="space-y-2" aria-labelledby="wog-h">
          <h2 id="wog-h" className="font-semibold">{t('waitOrGo')}</h2>
          {[...groups.values()].map((g) => (
            <div key={g.route_id + g.direction} className="card space-y-1 px-4 py-3">
              <Link to={`/route/${g.route_id}?d=${g.direction}`} className="font-semibold underline-offset-4 hover:underline">
                <ModeIcon mode={g.mode} /> {g.route} → {g.to}
              </Link>
              <WaitHint stopId={stopId} routeId={g.route_id} direction={g.direction} />
            </div>
          ))}
        </section>
      ) : null}
      <Link to={`/plan?from=${encodeURIComponent(stopId)}`} className="btn-primary w-full">🧭 {t('planTrip')}</Link>
    </div>
  )
}
