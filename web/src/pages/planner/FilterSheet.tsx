// Filter sheet (a modal dialog that slides up on phones): modes, walking, fare, transfers,
// step-free access and the women's travel option. Changes apply when the user taps Apply.
import { useEffect, useRef, useState } from 'react'
import type { Mode, PlanFilters } from '../../api'
import { ModeIcon } from '../../components'
import { useT } from '../../i18n'

const MODES: Mode[] = ['bus', 'mrts', 'metro']
const WALKS: (number | null)[] = [null, 5, 10, 15]
const FARES: (number | null)[] = [null, 15, 25, 40]
const TRANSFERS: (number | null)[] = [null, 1, 0]

export function activeFilterCount(f: PlanFilters): number {
  return (f.modes.length < 3 ? 1 : 0) + (f.max_walk_min != null ? 1 : 0) + (f.max_fare != null ? 1 : 0) +
    (f.max_transfers != null ? 1 : 0) + (f.step_free ? 1 : 0) + (f.women ? 1 : 0)
}

function Seg<T>({ label, options, value, onChange, fmt }: { label: string; options: T[]; value: T; onChange: (v: T) => void; fmt: (v: T) => string }) {
  return (
    <fieldset>
      <legend className="mb-1 text-sm font-medium">{label}</legend>
      <div className="flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
        {options.map((o) => (
          <button key={String(o)} type="button" className="seg" aria-pressed={o === value} onClick={() => onChange(o)}>{fmt(o)}</button>
        ))}
      </div>
    </fieldset>
  )
}

function Toggle({ id, label, hint, checked, onChange }: { id: string; label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label htmlFor={id} className="tap flex cursor-pointer items-start gap-3">
      <input id={id} type="checkbox" className="mt-1 h-6 w-6 shrink-0 accent-teal-700" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span><span className="font-medium">{label}</span><span className="block text-xs text-slate-600 dark:text-slate-400">{hint}</span></span>
    </label>
  )
}

export default function FilterSheet({ open, value, defaults, onClose, onApply }: {
  open: boolean; value: PlanFilters; defaults: PlanFilters; onClose: () => void; onApply: (f: PlanFilters) => void
}) {
  const t = useT()
  const ref = useRef<HTMLDialogElement>(null)
  const [f, setF] = useState<PlanFilters>(value)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) { setF(value); d.showModal() }
    if (!open && d.open) d.close()
  }, [open, value])
  const toggleMode = (m: Mode) => {
    const has = f.modes.includes(m)
    if (has && f.modes.length === 1) return   // keep at least one mode
    setF({ ...f, modes: has ? f.modes.filter((x) => x !== m) : [...f.modes, m] })
  }
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="filters-title"
      className="m-0 mt-auto w-full max-w-none rounded-t-3xl bg-white p-0 text-slate-900 shadow-2xl backdrop:bg-slate-950/50 sm:m-auto sm:max-w-lg sm:rounded-3xl dark:bg-slate-900 dark:text-slate-100">
      <form method="dialog" className="space-y-5 p-5" onSubmit={(e) => { e.preventDefault(); onApply(f); onClose() }}>
        <div className="flex items-center justify-between">
          <h2 id="filters-title" className="text-xl font-bold">{t('filters')}</h2>
          <button type="button" className="tap rounded-lg px-2" aria-label="Close" onClick={onClose}>✕</button>
        </div>
        <fieldset>
          <legend className="mb-1 text-sm font-medium">{t('modes')}</legend>
          <div className="flex flex-wrap gap-2">
            {MODES.map((m) => {
              const on = f.modes.includes(m)
              return (
                <button key={m} type="button" aria-pressed={on} onClick={() => toggleMode(m)}
                  className={`tap inline-flex items-center gap-2 rounded-full px-4 text-sm font-medium ring-1 ${on ? 'bg-brand text-white ring-brand' : 'ring-slate-300 dark:ring-slate-700'}`}>
                  <ModeIcon mode={m} /> {t(m)}
                </button>
              )
            })}
          </div>
        </fieldset>
        <Seg label={t('maxWalk')} options={WALKS} value={f.max_walk_min} onChange={(v) => setF({ ...f, max_walk_min: v })}
          fmt={(v) => (v == null ? t('any') : `${v} ${t('min')}`)} />
        <Seg label={t('maxFare')} options={FARES} value={f.max_fare} onChange={(v) => setF({ ...f, max_fare: v })}
          fmt={(v) => (v == null ? t('any') : `₹${v}`)} />
        <Seg label={t('maxTransfers')} options={TRANSFERS} value={f.max_transfers} onChange={(v) => setF({ ...f, max_transfers: v })}
          fmt={(v) => (v == null ? t('any') : v === 0 ? t('direct') : t('upTo1'))} />
        <div className="space-y-2">
          <h3 className="text-sm font-medium">{t('accessibility')}</h3>
          <Toggle id="f-step" label={t('stepFree')} hint={t('stepFreeHint')} checked={f.step_free} onChange={(v) => setF({ ...f, step_free: v })} />
          <Toggle id="f-women" label={t('women')} hint={t('womenHint')} checked={f.women} onChange={(v) => setF({ ...f, women: v })} />
        </div>
        <div className="flex gap-3 pt-1">
          <button type="button" className="btn-ghost flex-1" onClick={() => setF(defaults)}>{t('reset')}</button>
          <button type="submit" className="btn-primary flex-1">{t('apply')}</button>
        </div>
      </form>
    </dialog>
  )
}
