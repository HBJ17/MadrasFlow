// Departure time with a +/- window that grows and shrinks in 15-minute steps (15, 30, 45 ... 120).
import { useT } from '../../i18n'

export const STEP = 15
export const MAX_WINDOW = 120

export default function WindowStepper({ time, onTime, window, onWindow }: {
  time: string; onTime: (v: string) => void; window: number; onWindow: (v: number) => void
}) {
  const t = useT()
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <label htmlFor="when" className="mb-1 block text-sm font-medium">{t('departAt')}</label>
        <input id="when" type="time" className="input w-36" value={time} onChange={(e) => onTime(e.target.value)} />
      </div>
      <div>
        <span className="mb-1 block text-sm font-medium" id="win-label">{t('windowLabel')}</span>
        <div className="flex items-center gap-1" role="group" aria-labelledby="win-label">
          <button type="button" className="btn-ghost w-11 px-0 text-lg" aria-label={t('narrow')} disabled={window <= STEP}
            onClick={() => onWindow(Math.max(STEP, window - STEP))}>−</button>
          <output className="w-24 text-center font-semibold tabular-nums" aria-live="polite">± {window} {t('min')}</output>
          <button type="button" className="btn-ghost w-11 px-0 text-lg" aria-label={t('widen')} disabled={window >= MAX_WINDOW}
            onClick={() => onWindow(Math.min(MAX_WINDOW, window + STEP))}>+</button>
        </div>
      </div>
    </div>
  )
}
