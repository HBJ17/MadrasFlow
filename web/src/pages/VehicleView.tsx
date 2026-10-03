import { hhmm, usePolling, type VehicleInfo } from '../api'
import { LevelChip, LoadBar, SimBadge, Spinner, StaleBanner } from '../components'
import { useT } from '../i18n'
import { Link } from '../router'

export default function VehicleView({ vehicleId }: { vehicleId: string }) {
  const t = useT()
  const v = usePolling<VehicleInfo>(`/vehicle/${encodeURIComponent(vehicleId)}`)
  const d = v.data
  return (
    <div className="space-y-4">
      <button className="tap text-sm text-brand underline-offset-4 hover:underline dark:text-teal-300" onClick={() => history.back()}>← {t('back')}</button>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{t('vehicle')} {vehicleId}</h1>
        <SimBadge source={d?.data_source} />
      </div>
      <StaleBanner since={v.staleSince} error={!d ? v.error : null} onRetry={v.reload} />
      {v.loading && !d ? <Spinner /> : null}
      {d ? (
        <>
          <div className="card space-y-2 p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-600 dark:text-slate-300">{t('load')}</span>
              <LevelChip level={d.level} lf={d.load_factor} />
            </div>
            <LoadBar lf={d.load_factor} />
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {d.load ?? '–'} / {d.capacity} · <Link className="underline" to={`/route/${d.route_id}?d=${d.direction}`}>{d.route}</Link> · {d.last_stop} {hhmm(d.last_report)}
            </p>
          </div>
          <section className="space-y-2">
            <h2 className="font-semibold">{t('nextStops')}</h2>
            <ul className="card divide-y divide-slate-100 dark:divide-slate-800">
              {d.next_stops.map((s) => (
                <li key={s.stop_id} className="flex items-center gap-3 px-4 py-2">
                  <span className="flex-1">{s.name}</span>
                  <span className="w-12 text-right tabular-nums">{s.eta_min}′</span>
                  <span className="w-24 text-right"><LevelChip level={s.level} size="sm" /></span>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}
    </div>
  )
}
