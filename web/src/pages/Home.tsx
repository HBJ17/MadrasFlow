import { useMemo, useState } from 'react'
import { usePolling, type RouteInfo, type StopInfo, type StopOccupancy } from '../api'
import { LevelChip, ModeIcon, SimBadge, Spinner } from '../components'
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
    <Link to={`/stop/${encodeURIComponent(stop.stop_id)}`} className="card tap flex items-center gap-3 px-4 py-3">
      <ModeIcon mode={stop.mode} />
      <span className="flex-1 font-medium">{stop.name}</span>
      {v ? (
        <span className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          {v.route} · {v.eta_min}′ <LevelChip level={v.level} size="sm" />
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
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-bold">{t('tagline')}</h1>
        <SimBadge source={health.data?.data_source} />
      </div>

      <div className="relative">
        <label htmlFor="q" className="sr-only">{t('search')}</label>
        <input id="q" className="input" placeholder={t('search')} value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
        {(matches.length > 0 || routeMatches.length > 0) && (
          <ul className="card absolute z-10 mt-1 w-full divide-y divide-slate-100 overflow-hidden dark:divide-slate-800">
            {routeMatches.map((r) => (
              <li key={r.route_id}>
                <Link to={`/route/${r.route_id}`} className="tap flex items-center gap-2 px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-800">
                  <ModeIcon mode={r.mode} /> <b>{r.short_name}</b> <span className="text-sm text-slate-600 dark:text-slate-400">{r.long_name}</span>
                </Link>
              </li>
            ))}
            {matches.map((s) => (
              <li key={s.stop_id}>
                <Link to={`/stop/${encodeURIComponent(s.stop_id)}`} className="tap flex items-center gap-2 px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-800">
                  <ModeIcon mode={s.mode} /> {s.name} <span className="text-xs text-slate-600 dark:text-slate-400">{s.routes.join(', ').replace(/BUS_|_S\b/g, '')}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <button className="btn-primary w-full text-base" onClick={() => navigate('/plan')}>
        🧭 {t('planTrip')}
      </button>

      <section aria-labelledby="fav-h" className="space-y-2">
        <h2 id="fav-h" className="font-semibold">{t('favourites')}</h2>
        {fav.length === 0 ? <p className="text-sm text-slate-600 dark:text-slate-400">{t('noFav')}</p> : null}
        {stops.data?.filter((s) => fav.includes(s.stop_id)).map((s) => <FavStop key={s.stop_id} stop={s} />)}
      </section>

      <section aria-labelledby="near-h" className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 id="near-h" className="font-semibold">{t('nearby')}</h2>
          <button className="btn-ghost text-sm" onClick={findNear}>📍 {t('findNearby')}</button>
        </div>
        {near?.map((s) => (
          <Link key={s.stop_id} to={`/stop/${encodeURIComponent(s.stop_id)}`} className="card tap flex items-center gap-3 px-4 py-3">
            <ModeIcon mode={s.mode} /> {s.name}
          </Link>
        ))}
      </section>

      <section aria-labelledby="routes-h" className="space-y-2">
        <h2 id="routes-h" className="font-semibold">{t('routes')}</h2>
        {routes.loading && !routes.data ? <Spinner /> : null}
        <ul className="grid gap-2 sm:grid-cols-2">
          {routes.data?.map((r) => (
            <li key={r.route_id}>
              <Link to={`/route/${r.route_id}`} className="card tap flex h-full items-center gap-3 px-4 py-3">
                <ModeIcon mode={r.mode} />
                <span className="min-w-12 text-lg font-bold">{r.short_name}</span>
                <span className="text-sm text-slate-600 dark:text-slate-300">{r.long_name.replace(/\(.*\)/, '')}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
      <p className="text-xs text-slate-600 dark:text-slate-400">{t('simulatedLong')}</p>
    </div>
  )
}
