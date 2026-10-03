import { Suspense, useEffect, useState } from 'react'
import { lazyReload } from './lazyReload'
import { Link, useLocation } from './router'
import { LangContext, type Lang, useT } from './i18n'
import { Spinner } from './components'
import Home from './pages/Home'
import RouteView from './pages/RouteView'
import StopView from './pages/StopView'
import Planner from './pages/Planner'
import VehicleView from './pages/VehicleView'

// The depot dashboard (charts) is a separate chunk so the commuter bundle stays small.
const Depot = lazyReload(() => import('./pages/Depot'))

function Header() {
  const t = useT()
  const { path } = useLocation()
  const depot = path.startsWith('/depot')
  return (
    <header className="sticky top-0 z-20 bg-brand text-white shadow">
      <div className={`mx-auto flex items-center gap-3 px-4 py-2 ${depot ? 'max-w-7xl' : 'max-w-2xl'}`}>
        <Link to={depot ? '/depot' : '/'} className="tap flex items-center gap-2 font-bold">
          <img src="/icon.svg" alt="" width={28} height={28} />
          <span>{t('app')}</span>
          <span className="hidden text-sm font-normal opacity-90 sm:inline">· {depot ? t('depot') : t('tagline')}</span>
        </Link>
        <span className="flex-1" />
        <LangToggle />
        <Link to={depot ? '/' : '/depot'} className="tap flex items-center rounded-lg px-2 text-sm underline-offset-4 hover:underline">
          {depot ? t('commuter') : t('depot')}
        </Link>
      </div>
    </header>
  )
}

function LangToggle() {
  return (
    <LangContext.Consumer>
      {({ lang, setLang }) => (
        <button
          className="tap rounded-lg px-2 text-sm ring-1 ring-white/40"
          onClick={() => setLang(lang === 'en' ? 'ta' : 'en')}
          aria-label={lang === 'en' ? 'தமிழில் காட்டு' : 'Show in English'}
        >
          {lang === 'en' ? 'தமிழ்' : 'EN'}
        </button>
      )}
    </LangContext.Consumer>
  )
}

function Routes() {
  const { path } = useLocation()
  const seg = path.split('/').filter(Boolean)
  if (seg[0] === 'route' && seg[1]) return <RouteView routeId={decodeURIComponent(seg[1])} />
  if (seg[0] === 'stop' && seg[1]) return <StopView stopId={decodeURIComponent(seg[1])} />
  if (seg[0] === 'plan') return <Planner />
  if (seg[0] === 'vehicle' && seg[1]) return <VehicleView vehicleId={decodeURIComponent(seg[1])} />
  if (seg[0] === 'depot') return <Suspense fallback={<Spinner />}><Depot /></Suspense>
  return <Home />
}

export default function App() {
  const [lang, setLang] = useState<Lang>(() => {
    try { return (localStorage.getItem('kt-lang') as Lang) || 'en' } catch { return 'en' }
  })
  useEffect(() => {
    try { localStorage.setItem('kt-lang', lang) } catch { /* ignore */ }
    document.documentElement.lang = lang
  }, [lang])
  const { path } = useLocation()
  return (
    <LangContext.Provider value={{ lang, setLang }}>
      <Header />
      <main className={`mx-auto px-4 pb-16 pt-4 ${path.startsWith('/depot') ? 'max-w-7xl' : 'max-w-2xl'}`}>
        <Routes />
      </main>
    </LangContext.Provider>
  )
}
