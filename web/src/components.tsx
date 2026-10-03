import type { DataSource, Level } from './api'
import { hhmm, pct } from './api'
import { useT } from './i18n'

export function LevelChip({ level, lf, size = 'md' }: { level: Level | null | undefined; lf?: number | null; size?: 'sm' | 'md' }) {
  const t = useT()
  const label = level ? t(level) : '–'
  const aria = level ? `${t(level)}, ${lf != null ? Math.round(lf * 100) + ' percent ' + t('full') : ''}` : 'no forecast'
  return (
    <span
      role="img"
      aria-label={aria}
      className={`lvl-${level ?? 'none'} inline-flex items-center justify-center rounded-full font-semibold whitespace-nowrap ${
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'
      }`}
    >
      {label}
      {lf != null && size === 'md' ? <span className="ml-1.5 font-normal opacity-90">{pct(lf)}</span> : null}
    </span>
  )
}

export function SimBadge({ source }: { source?: DataSource | null }) {
  const t = useT()
  if (!source || source === 'camera' || source === 'none') return null
  return (
    <span
      title={t('simulatedLong')}
      className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900 ring-1 ring-amber-300 dark:bg-amber-900/40 dark:text-amber-200 dark:ring-amber-700"
    >
      <span aria-hidden>◆</span> {t('simulated')}
      {source === 'mixed' ? ' + camera' : ''}
    </span>
  )
}

export function StaleBanner({ since, error, onRetry }: { since: Date | null; error?: string | null; onRetry?: () => void }) {
  const t = useT()
  if (!since && !error) return null
  return (
    <div role="status" className="mb-3 flex items-center justify-between gap-3 rounded-xl bg-slate-800 px-4 py-2 text-sm text-white">
      <span>{since ? `${t('lastUpdated')} ${hhmm(since)}` : error}</span>
      {onRetry ? <button className="tap rounded-lg px-3 underline" onClick={onRetry}>{t('retry')}</button> : null}
    </div>
  )
}

export function ModeIcon({ mode }: { mode: string }) {
  const m: Record<string, [string, string]> = { bus: ['🚌', 'Bus'], metro: ['🚇', 'Metro'], mrts: ['🚆', 'MRTS'] }
  const [icon, label] = m[mode] ?? ['•', mode]
  return <span role="img" aria-label={label}>{icon}</span>
}

export function Spinner() {
  const t = useT()
  return <p className="py-8 text-center text-slate-600 dark:text-slate-400" role="status">{t('loading')}</p>
}

export function LoadBar({ lf }: { lf: number | null | undefined }) {
  if (lf == null) return <div className="h-2 w-full rounded bg-slate-200 dark:bg-slate-800" />
  const w = Math.min(100, Math.round((lf / 1.3) * 100))
  const level = lf < 0.4 ? 'LOW' : lf < 0.75 ? 'MEDIUM' : lf < 1 ? 'HIGH' : 'CROWDED'
  return (
    <div className="relative h-2 w-full rounded bg-slate-200 dark:bg-slate-800" aria-hidden>
      <div className={`bar-${level} h-2 rounded`} style={{ width: `${w}%` }} />
      <div className="absolute top-[-2px] h-3 w-px bg-slate-500" style={{ left: `${(1 / 1.3) * 100}%` }} title="capacity" />
    </div>
  )
}
