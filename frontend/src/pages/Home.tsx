import { useMemo, useState } from 'react'
import { usePolling, type RouteInfo, type StopInfo, type StopOccupancy } from '../api'
import { Icon, LevelChip, ModeIcon, ModeTile, SimBadge, Spinner } from '../components'
import { useT } from '../i18n'
import { Link, navigate } from '../router'

export function useFavourites() {
  const [fav, setFav] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('kt-fav') || '[]') } catch { return [] }
  })
  const toggle = (id: string) => {
    const next = fav.includes(id) ? fav.filter((x) => x !== id) : [...fav, id]
    setFav(next)
    try { localStorage.setItem('kt-fav', JSON.stringify(next)) } catch { /* ignore */ }
  }
  return { fav, toggle }
}

function FavStop({ stop }: { stop: StopInfo }) {
  const occ = usePolling<StopOccupancy>(`/occupancy/stop/${encodeURIComponent(stop.stop_id)}?n=2`)
  const v = occ.data?.vehicles?.[0]
  return (
    <Link to={`/stop/${encodeURIComponent(stop.stop_id)}`} className="card tap flex items-center gap-3 px-3 py-3 transition hover:bg-slate-100 active:scale-[0.99] dark:hover:bg-[#1f232d]">
      <ModeTile mode={stop.mode} />
      <span className="flex-1 font-display font-semibold text-[#002046] dark:text-navy-soft">{stop.name}</span>
      {v ? (
        <span className="flex items-center gap-2 font-mono text-xs font-semibold text-slate-600 dark:text-slate-300">
          <span className="rounded bg-slate-200 px-1.5 py-0.5 dark:bg-[#2d3341]">{v.route}</span> {v.eta_min}′ <LevelChip level={v.level} size="sm" />
        </span>
      ) : null}
    </Link>
  )
}

export default function Home() {
  const t = useT()
  const routes = usePolling<RouteInfo[]>('/routes', 3600_000)
  const stops = usePolling<StopInfo[]>('/stops', 3600_000)
  const health = usePolling<{ data_source: 'twin' | 'camera' | 'mixed' | 'none' }>('/health', 60_000)
  const { fav } = useFavourites()
  const [q, setQ] = useState('')
  const [near, setNear] = useState<StopInfo[] | null>(null)

  const matches = useMemo(() => {
    if (!q.trim() || !stops.data) return []
    const s = q.toLowerCase()
    const seen = new Set<string>()
    return stops.data.filter((x) => x.name.toLowerCase().includes(s) && !seen.has(x.name + x.mode) && seen.add(x.name + x.mode)).slice(0, 8)
  }, [q, stops.data])
  const routeMatches = useMemo(() => {
    if (!q.trim() || !routes.data) return []
    const s = q.toLowerCase()
    return routes.data.filter((r) => r.short_name.toLowerCase().includes(s) || r.long_name.toLowerCase().includes(s))
  }, [q, routes.data])

  const findNear = () => {
    navigator.geolocation?.getCurrentPosition((p) => {
      const { latitude: la, longitude: lo } = p.coords
      const d = (s: StopInfo) => (s.lat - la) ** 2 + ((s.lon - lo) * Math.cos((la * Math.PI) / 180)) ** 2
      setNear([...(stops.data || [])].sort((a, b) => d(a) - d(b)).slice(0, 5))
    })
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="ledger">{t('app')}</span>
          <SimBadge source={health.data?.data_source} />
        </div>
        <h1 className="text-[28px] font-bold leading-[1.1] text-[#002046] sm:text-[32px] dark:text-navy-soft">{t('tagline')}</h1>
      </div>

      <div className="relative">
        <label htmlFor="q" className="sr-only">{t('search')}</label>
        <span aria-hidden className="pointer-events-none absolute left-3 top-[22px] -translate-y-1/2 text-slate-500"><Icon name="pin" /></span>
        <input id="q" className="input pl-10" placeholder={t('search')} value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
        {(matches.length > 0 || routeMatches.length > 0) && (
          <ul className="card absolute z-10 mt-1 w-full divide-y divide-slate-200 overflow-hidden shadow-lg dark:divide-white/5">
            {routeMatches.map((r) => (
              <li key={r.route_id}>
                <Link to={`/route/${r.route_id}`} className="tap flex items-center gap-2 px-4 py-2 hover:bg-slate-100 dark:hover:bg-slate-800">
                  <ModeIcon mode={r.mode} /> <b className="font-display text-[#002046] dark:text-navy-soft">{r.short_name}</b> <span className="text-sm text-slate-600 dark:text-slate-400">{r.long_name}</span>
                </Link>
              </li>
            ))}
            {matches.map((s) => (
              <li key={s.stop_id}>
                <Link to={`/stop/${encodeURIComponent(s.stop_id)}`} className="tap flex items-center gap-2 px-4 py-2 hover:bg-slate-100 dark:hover:bg-slate-800">
                  <ModeIcon mode={s.mode} /> {s.name} <span className="font-mono text-[11px] text-slate-600 dark:text-slate-400">{s.routes.join(', ').replace(/BUS_|_S\b/g, '')}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <button className="btn-primary h-12 w-full text-base" onClick={() => navigate('/plan')}>
        <Icon name="explore" className="h-5 w-5 text-lime dark:text-[#002046]" /> {t('planTrip')}
      </button>

      <section aria-labelledby="fav-h" className="space-y-2">
        <h2 id="fav-h" className="ledger">{t('favourites')}</h2>
        {fav.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 px-4 py-3 text-sm text-slate-600 dark:border-white/10 dark:text-slate-400">{t('noFav')}</p> : null}
        {stops.data?.filter((s) => fav.includes(s.stop_id)).map((s) => <FavStop key={s.stop_id} stop={s} />)}
      </section>

      <section aria-labelledby="near-h" className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 id="near-h" className="ledger">{t('nearby')}</h2>
          <button className="btn-ghost text-sm" onClick={findNear}><Icon name="pin" className="h-4 w-4" /> {t('findNearby')}</button>
        </div>
        {near?.map((s) => (
          <Link key={s.stop_id} to={`/stop/${encodeURIComponent(s.stop_id)}`} className="card tap flex items-center gap-3 px-3 py-3 transition hover:bg-slate-100 active:scale-[0.99] dark:hover:bg-[#1f232d]">
            <ModeTile mode={s.mode} small /> <span className="font-display font-semibold text-[#002046] dark:text-navy-soft">{s.name}</span>
          </Link>
        ))}
      </section>

      <section aria-labelledby="routes-h" className="space-y-2">
        <h2 id="routes-h" className="ledger">{t('routes')}</h2>
        {routes.loading && !routes.data ? <Spinner /> : null}
        <ul className="grid gap-2 sm:grid-cols-2">
          {routes.data?.map((r) => (
            <li key={r.route_id}>
              <Link to={`/route/${r.route_id}`} className="card tap flex h-full items-center gap-3 px-3 py-3 transition hover:bg-slate-100 active:scale-[0.99] dark:hover:bg-[#1f232d]">
                <ModeTile mode={r.mode} />
                <span className="flex min-w-0 flex-col">
                  <span className="font-display text-lg font-bold leading-tight text-[#002046] dark:text-navy-soft">{r.short_name}</span>
                  <span className="text-sm text-slate-600 dark:text-slate-300">{r.long_name.replace(/\(.*\)/, '')}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
      <p className="border-t border-slate-200 pt-3 font-mono text-[11px] text-slate-600 dark:border-white/5 dark:text-slate-400">{t('simulatedLong')}</p>
    </div>
  )
}
