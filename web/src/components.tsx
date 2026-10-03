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
      className={`lvl-${level ?? 'none'} inline-flex items-center justify-center rounded-md font-mono font-bold uppercase tracking-[0.06em] whitespace-nowrap ${
        size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs'
      }`}
    >
      {label}
      {lf != null && size === 'md' ? <span className="ml-1.5 font-medium opacity-80">{pct(lf)}</span> : null}
    </span>
  )
}

export function SimBadge({ source }: { source?: DataSource | null }) {
  const t = useT()
  if (!source || source === 'camera' || source === 'none') return null
  return (
    <span
      title={t('simulatedLong')}
      className="inline-flex items-center gap-1.5 rounded-md bg-amber-200 px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-amber-950 dark:bg-amber-400/20 dark:text-amber-200"
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-amber-700 dark:bg-amber-300" /> {t('simulated')}
      {source === 'mixed' ? ' + camera' : ''}
    </span>
  )
}

export function StaleBanner({ since, error, onRetry }: { since: Date | null; error?: string | null; onRetry?: () => void }) {
  const t = useT()
  if (!since && !error) return null
  return (
    <div role="status" className="mb-3 flex items-center justify-between gap-3 rounded-xl bg-[#002046] px-4 py-2 text-sm text-white ring-1 ring-white/10 dark:bg-slate-800">
      <span className="flex items-center gap-2"><span aria-hidden className="h-2 w-2 rounded-full bg-amber-300" />{since ? `${t('lastUpdated')} ${hhmm(since)}` : error}</span>
      {onRetry ? <button className="tap rounded-lg px-3 font-mono text-xs font-semibold uppercase tracking-wider text-lime" onClick={onRetry}>{t('retry')}</button> : null}
    </div>
  )
}

// Inline glyphs (Material Symbols shapes) so icons render offline and without an icon font.
const PATHS: Record<string, string> = {
  bus: 'M4 16c0 .88.39 1.67 1 2.22V20c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h8v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1.78c.61-.55 1-1.34 1-2.22V6c0-3.5-3.58-4-8-4s-8 .5-8 4v10zm3.5 1c-.83 0-1.5-.67-1.5-1.5S6.67 14 7.5 14s1.5.67 1.5 1.5S8.33 17 7.5 17zm9 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm1.5-6H6V6h12v5z',
  metro: 'M17.8 2.8C16 2.09 13.86 2 12 2s-4 .09-5.8.8C3.53 3.84 2 6.05 2 8.86V22h20V8.86c0-2.81-1.53-5.02-4.2-6.06zM9.17 20l1.5-1.5h2.66l1.5 1.5H9.17zm-2.16-6V9h10v5h-10zm9.49 2c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-9-2c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zM20 20h-3.5v-.38l-1.15-1.16c1.49-.17 2.65-1.42 2.65-2.96V9c0-2.63-3-3-6-3s-6 .37-6 3v6.5c0 1.54 1.16 2.79 2.65 2.96L7.5 19.62V20H4V8.86c0-2 1.01-3.45 2.93-4.2C8.41 4.08 10.32 4 12 4s3.59.08 5.07.66c1.92.75 2.93 2.2 2.93 4.2V20z',
  mrts: 'M12 2c-4 0-8 .5-8 4v9.5C4 17.43 5.57 19 7.5 19L6 20.5v.5h2.23l2-2H14l2 2h2v-.5L16.5 19c1.93 0 3.5-1.57 3.5-3.5V6c0-3.5-3.58-4-8-4zM7.5 17c-.83 0-1.5-.67-1.5-1.5S6.67 14 7.5 14s1.5.67 1.5 1.5S8.33 17 7.5 17zm3.5-7H6V6h5v4zm2 0V6h5v4h-5zm3.5 7c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z',
  explore: 'M12 10.9c-.61 0-1.1.49-1.1 1.1s.49 1.1 1.1 1.1c.61 0 1.1-.49 1.1-1.1s-.49-1.1-1.1-1.1zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm2.19 12.19L6 18l3.81-8.19L18 6l-3.81 8.19z',
  pin: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  walk: 'M13.5 5.5c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zM9.8 8.9L7 23h2.1l1.8-8 2.1 2v6h2v-7.5l-2.1-2 .6-3C14.8 12 16.8 13 19 13v-2c-1.9 0-3.5-1-4.3-2.4l-1-1.6c-.4-.6-1-1-1.7-1-.3 0-.5.1-.8.1L6 8.3V13h2V9.6l1.8-.7',
  back: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  star: 'M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z',
  starOutline: 'M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z',
  bulb: 'M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z',
  moon: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.39 5.39 0 0 1-4.4 2.26 5.4 5.4 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  sun: 'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1zM5.99 4.58a.996.996 0 0 0-1.41 0 .996.996 0 0 0 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0s.39-1.03 0-1.41L5.99 4.58zm12.37 12.37a.996.996 0 0 0-1.41 0 .996.996 0 0 0 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0a.996.996 0 0 0 0-1.41l-1.06-1.06zm1.06-10.96a.996.996 0 0 0 0-1.41.996.996 0 0 0-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06zM7.05 18.36a.996.996 0 0 0 0-1.41.996.996 0 0 0-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06z',
  map: 'M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z',
}

export function Icon({ name, className = 'h-[18px] w-[18px]' }: { name: keyof typeof PATHS | string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`inline-block shrink-0 fill-current align-[-0.2em] ${className}`} aria-hidden focusable="false">
      <path d={PATHS[name] ?? ''} />
    </svg>
  )
}

const MODE_LABEL: Record<string, string> = { bus: 'Bus', metro: 'Metro', mrts: 'MRTS' }

export function ModeIcon({ mode }: { mode: string }) {
  const label = MODE_LABEL[mode]
  if (!label) return <span role="img" aria-label={mode}>•</span>
  return <span role="img" aria-label={label} className="inline-flex"><Icon name={mode} /></span>
}

// Mode glyph on a coloured tile, used at the start of list rows.
const TILE: Record<string, string> = {
  metro: 'bg-[#002046] text-white dark:bg-[#1b365d] dark:text-navy-soft',
  bus: 'bg-amber-400 text-amber-900 dark:bg-amber-400/25 dark:text-amber-200',
  mrts: 'bg-slate-200 text-[#002046] dark:bg-[#252b36] dark:text-navy-soft',
}

export function ModeTile({ mode, small }: { mode: string; small?: boolean }) {
  return (
    <span role="img" aria-label={MODE_LABEL[mode] ?? mode}
      className={`tile ${small ? 'h-8 w-8' : ''} ${TILE[mode] ?? 'bg-slate-200 text-slate-700'}`}>
      <Icon name={mode} className={small ? 'h-[17px] w-[17px]' : 'h-5 w-5'} />
    </span>
  )
}

export function BackButton({ label }: { label: string }) {
  return (
    <button className="tap -ml-2 inline-flex items-center gap-1.5 rounded-full px-2 font-mono text-xs font-semibold uppercase tracking-[0.08em] text-slate-600 transition-colors hover:bg-slate-100 hover:text-[#002046] dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-navy-soft" onClick={() => history.back()}>
      <Icon name="back" className="h-4 w-4" /> {label}
    </button>
  )
}

export function Spinner() {
  const t = useT()
  return (
    <p className="flex items-center justify-center gap-2 py-8 font-mono text-xs font-semibold uppercase tracking-[0.08em] text-slate-600 dark:text-slate-400" role="status">
      <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-emerald-600 dark:bg-emerald-400" />{t('loading')}
    </p>
  )
}

export function LoadBar({ lf }: { lf: number | null | undefined }) {
  if (lf == null) return <div className="h-2 w-full rounded-full bg-slate-200 dark:bg-slate-800" />
  const w = Math.min(100, Math.round((lf / 1.3) * 100))
  const level = lf < 0.4 ? 'LOW' : lf < 0.75 ? 'MEDIUM' : lf < 1 ? 'HIGH' : 'CROWDED'
  return (
    <div className="relative h-2 w-full rounded-full bg-slate-200 dark:bg-slate-800" aria-hidden>
      <div className={`bar-${level} h-2 rounded-full transition-all duration-500`} style={{ width: `${w}%` }} />
      <div className="absolute top-[-3px] h-3.5 w-0.5 rounded bg-[#002046] dark:bg-navy-soft" style={{ left: `${(1 / 1.3) * 100}%` }} title="capacity" />
    </div>
  )
}
