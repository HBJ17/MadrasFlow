// "From" field: the commuter's GPS position snapped to the nearest stop by default, or a typed stop.
import { useEffect, useState } from 'react'
import { getJSON, type NearStop, type StopInfo } from '../../api'
import { useT } from '../../i18n'
import StopPicker from './StopPicker'

export interface Origin { stop_id: string; name: string; walk_min: number; gps: boolean }

export default function LocationField({ stops, initialStop, onChange }: {
  stops: StopInfo[]; initialStop: StopInfo | null; onChange: (o: Origin | null) => void
}) {
  const t = useT()
  const [mode, setMode] = useState<'gps' | 'stop'>(initialStop ? 'stop' : 'gps')
  const [state, setState] = useState<'idle' | 'locating' | 'ok' | 'failed'>('idle')
  const [near, setNear] = useState<NearStop | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [picked, setPicked] = useState<StopInfo | null>(initialStop)

  const locate = () => {
    setMode('gps'); setState('locating'); setMsg(null); onChange(null)
    if (!('geolocation' in navigator)) { setState('failed'); setMsg(t('locationDenied')); setMode('stop'); return }
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try {
        const { data } = await getJSON<NearStop[]>(`/stops/nearest?lat=${pos.coords.latitude}&lon=${pos.coords.longitude}&limit=1`)
        setNear(data[0]); setState('ok')
        onChange({ stop_id: data[0].stop_id, name: data[0].name, walk_min: data[0].walk_min, gps: true })
      } catch (e) { setState('failed'); setMsg(String((e as Error).message)); setMode('stop') }
    }, () => { setState('failed'); setMsg(t('locationDenied')); setMode('stop') }, { timeout: 8000, maximumAge: 60000 })
  }

  useEffect(() => {
    if (mode === 'gps' && state === 'idle') locate()
    if (initialStop) onChange({ stop_id: initialStop.stop_id, name: initialStop.name, walk_min: 0, gps: false })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (mode === 'stop') {
    return (
      <div className="space-y-1">
        <StopPicker id="from" label={t('from')} stops={stops} value={picked}
          onChange={(s) => { setPicked(s); onChange(s ? { stop_id: s.stop_id, name: s.name, walk_min: 0, gps: false } : null) }} />
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          {msg ? <span role="status" className="text-slate-600 dark:text-slate-400">{msg}</span> : <span />}
          <button type="button" className="tap text-brand underline-offset-4 hover:underline dark:text-teal-300" onClick={locate}>◎ {t('useLocation')}</button>
        </div>
      </div>
    )
  }
  return (
    <div>
      <span className="mb-1 block text-sm font-medium">{t('from')}</span>
      <div className="input flex items-center justify-between gap-2">
        <span className="truncate">
          ◎ {t('currentLocation')}
          {state === 'locating' ? <span className="text-slate-600 dark:text-slate-400"> · {t('locating')}</span> : null}
          {state === 'ok' && near ? <span className="text-slate-600 dark:text-slate-400"> · {t('near')} {near.name} ({Math.round(near.walk_min)} {t('minWalk')})</span> : null}
        </span>
        <button type="button" className="tap shrink-0 text-sm text-brand underline-offset-4 hover:underline dark:text-teal-300" onClick={() => { setMode('stop'); onChange(null) }}>{t('useStop')}</button>
      </div>
    </div>
  )
}
