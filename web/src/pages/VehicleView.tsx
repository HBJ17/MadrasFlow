import { hhmm, usePolling, type VehicleInfo } from '../api'
import { BackButton, LevelChip, LoadBar, SimBadge, Spinner, StaleBanner } from '../components'
import { useT } from '../i18n'
import { Link } from '../router'

export default function VehicleView({ vehicleId }: { vehicleId: string }) {
  const t = useT()
  const v = usePolling<VehicleInfo>(`/vehicle/${encodeURIComponent(vehicleId)}`)
  const d = v.data
  return (
    <div className="space-y-4">
      <BackButton label={t('back')} />
      <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
        <h1 className="text-[28px] font-bold leading-none text-[#002046] dark:text-navy-soft"><span className="ledger mb-1.5 block">{t('vehicle')}</span>{vehicleId}</h1>
        <SimBadge source={d?.data_source} />
      </div>
      <StaleBanner since={v.staleSince} error={!d ? v.error : null} onRetry={v.reload} />
      {v.loading && !d ? <Spinner /> : null}
      {d ? (
        <>
          <div className="card space-y-3 p-4">
            <div className="flex items-center justify-between">
              <span className="ledger">{t('load')}</span>
              <LevelChip level={d.level} lf={d.load_factor} />
            </div>
            <LoadBar lf={d.load_factor} />
            <p className="border-t border-slate-200 pt-2.5 font-mono text-xs text-slate-600 dark:border-white/5 dark:text-slate-300">
              <b className="text-ink dark:text-slate-100">{d.load ?? '–'} / {d.capacity}</b> · <Link className="font-semibold text-[#002046] underline dark:text-navy-soft" to={`/route/${d.route_id}?d=${d.direction}`}>{d.route}</Link> · {d.last_stop} {hhmm(d.last_report)}
            </p>
          </div>
          <section className="space-y-2">
            <h2 className="ledger">{t('nextStops')}</h2>
            <ul className="card divide-y divide-slate-200 dark:divide-white/5">
              {d.next_stops.map((s) => (
                <li key={s.stop_id} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="min-w-0 flex-1 font-medium">{s.name}</span>
                  <span className="w-10 shrink-0 text-right font-mono text-sm font-semibold tabular-nums">{s.eta_min}′</span>
                  <span className="w-20 shrink-0 text-right"><LevelChip level={s.level} size="sm" /></span>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}
    </div>
  )
}
