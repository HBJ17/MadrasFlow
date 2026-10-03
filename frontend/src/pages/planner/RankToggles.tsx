// Ranking criteria. Crowd and arrival time are ticked by default and can be unticked.
import type { RankKey } from '../../api'
import { useT } from '../../i18n'

const KEYS: [RankKey, 'rankCrowd' | 'rankEta' | 'rankCost' | 'rankWalk' | 'rankTransfers'][] = [
  ['crowd', 'rankCrowd'], ['eta', 'rankEta'], ['cost', 'rankCost'], ['walk', 'rankWalk'], ['transfers', 'rankTransfers'],
]
export const DEFAULT_RANK: RankKey[] = ['crowd', 'eta']

export default function RankToggles({ value, onChange }: { value: RankKey[]; onChange: (v: RankKey[]) => void }) {
  const t = useT()
  return (
    <fieldset>
      <legend className="ledger mb-1.5">{t('rankBy')}</legend>
      <div className="flex flex-wrap gap-2">
        {KEYS.map(([k, label]) => {
          const on = value.includes(k)
          return (
            <label key={k} className={`tap inline-flex cursor-pointer items-center gap-2 rounded-full px-3 font-display text-sm font-semibold ring-1 transition focus-within:ring-2 focus-within:ring-sky-500 ${
              on ? 'brand-fill ring-transparent' : 'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-[#1e232e] dark:text-slate-300 dark:ring-white/10'}`}>
              <input type="checkbox" className="sr-only" checked={on} onChange={() => onChange(on ? value.filter((x) => x !== k) : [...value, k])} />
              <span aria-hidden className={on ? 'text-lime dark:text-emerald-600' : ''}>{on ? '✓' : '+'}</span> {t(label)}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
