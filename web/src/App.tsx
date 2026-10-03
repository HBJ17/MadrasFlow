import { Suspense, useEffect, useState } from 'react'
import { lazyReload } from './lazyReload'
import { Link, useLocation } from './router'
import { LangContext, type Lang, useT } from './i18n'
import { Icon, Spinner } from './components'
import { setDark, useDark } from './theme'
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
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-paper/90 backdrop-blur-xl dark:border-white/5 dark:bg-slate-950/90">
      <div className={`mx-auto flex h-14 items-center gap-1 px-3 sm:gap-2 sm:px-4 ${depot ? 'max-w-7xl' : 'max-w-2xl'}`}>
        <Link to={depot ? '/depot' : '/'} className="tap flex min-w-0 items-center gap-2">
          <span className="relative flex h-2.5 w-2.5 shrink-0" aria-hidden>
            <span className="pulse-ring absolute inset-0 rounded-full bg-emerald-400/70" />
            <span className="relative h-2.5 w-2.5 rounded-full bg-emerald-600 dark:bg-emerald-400" />
          </span>
          <span className="truncate font-display text-base font-bold uppercase tracking-tight text-[#002046] dark:text-navy-soft">{t('app')}</span>
          <span className="ledger hidden truncate rounded bg-slate-100 px-1.5 py-0.5 text-[10px] sm:inline dark:bg-[#1e232e] dark:text-navy-soft/80">{depot ? t('depot') : t('tagline')}</span>
        </Link>
        <span className="flex-1" />
        <ThemeToggle />
        <LangToggle />
        <Link to={depot ? '/' : '/depot'} className="tap flex shrink-0 items-center whitespace-nowrap rounded-full px-2 font-display sm:px-3 text-sm font-semibold text-[#002046] transition-colors hover:bg-slate-100 dark:text-navy-soft dark:hover:bg-white/10">
          {depot ? t('commuter') : <><span className="sm:hidden">{t('depotShort')}</span><span className="hidden sm:inline">{t('depot')}</span></>}
        </Link>
      </div>
    </header>
  )
}

function ThemeToggle() {
  const dark = useDark()
  return (
    <button
      type="button"
      className="tap flex shrink-0 items-center justify-center rounded-full text-slate-600 transition-colors hover:bg-slate-100 active:scale-95 dark:text-navy-soft dark:hover:bg-white/10"
      onClick={() => setDark(!dark)}
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={dark ? 'Light theme' : 'Dark theme'}
    >
      <Icon name={dark ? 'sun' : 'moon'} className="h-5 w-5" />
    </button>
  )
}

function LangToggle() {
  return (
    <LangContext.Consumer>
      {({ lang, setLang }) => (
        <button
          className="tap flex shrink-0 items-center justify-center rounded-full px-2.5 font-display text-sm font-semibold text-[#002046] transition-colors hover:bg-slate-100 dark:text-navy-soft dark:hover:bg-white/10"
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
  return <Planner />
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
      <main className={`mx-auto px-4 pb-16 pt-5 ${path.startsWith('/depot') ? 'max-w-7xl' : 'max-w-2xl'}`}>
        <Routes />
      </main>
    </LangContext.Provider>
  )
}
