import { useMemo, useState } from 'react'
import type { StopInfo } from '../../api'
import { ModeIcon } from '../../components'

export default function StopPicker({ id, label, stops, value, onChange }: {
  id: string; label: string; stops: StopInfo[]; value: StopInfo | null; onChange: (s: StopInfo | null) => void
}) {
  const [q, setQ] = useState(value?.name ?? '')
  const [open, setOpen] = useState(false)
  const opts = useMemo(() => {
    const s = q.toLowerCase()
    const seen = new Set<string>()
    return stops.filter((x) => x.name.toLowerCase().includes(s) && !seen.has(x.station_id) && seen.add(x.station_id)).slice(0, 8)
  }, [q, stops])
  return (
    <div className="relative">
      <label htmlFor={id} className="ledger mb-1.5 block">{label}</label>
      <input id={id} className="input" value={q} autoComplete="off" role="combobox" aria-expanded={open} aria-controls={`${id}-list`}
        onChange={(e) => { setQ(e.target.value); setOpen(true); onChange(null) }} onFocus={() => setOpen(true)} />
      {open && q && opts.length > 0 ? (
        <ul id={`${id}-list`} role="listbox" className="card absolute z-10 mt-1 w-full divide-y divide-slate-200 overflow-hidden shadow-lg dark:divide-white/5">
          {opts.map((s) => (
            <li key={s.stop_id} role="option" aria-selected={value?.stop_id === s.stop_id}>
              <button type="button" className="tap flex w-full items-center gap-2 px-3 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => { onChange(s); setQ(s.name); setOpen(false) }}>
                <ModeIcon mode={s.mode} /> {s.name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
