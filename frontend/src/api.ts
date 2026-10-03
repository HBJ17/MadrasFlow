// Thin API client. Low-bandwidth rules: small JSON, poll every 30 s only while the tab is
// visible, exponential back-off on failure, and fall back to the last good response (shown with
// a "Last updated hh:mm" banner) when offline.
import { useEffect, useRef, useState } from 'react'

export const API = '/api/v1'

export type Level = 'LOW' | 'MEDIUM' | 'HIGH' | 'CROWDED'
export type DataSource = 'twin' | 'camera' | 'mixed' | 'none'

export interface RouteInfo {
  route_id: string; short_name: string; long_name: string; mode: 'bus' | 'mrts' | 'metro'
  operator: string; depot: string; capacity_total: number; stops: number
  directions: { direction: number; from: string; to: string }[]
}
export interface StopInfo { stop_id: string; name: string; lat: number; lon: number; mode: string; stop_type: string; station_id: string; routes: string[] }
export interface StripStop {
  stop_id: string; name: string; seq: number; eta_min: number | null; vehicle_id: string | null
  level: Level | null; load_factor: number | null; lo: number | null; hi: number | null
  source: string | null; stale: boolean | null; f: (number | null)[][]
}
export interface RouteOccupancy {
  route_id: string; short_name: string; mode: string; direction: number; now: string; made_at: string | null
  data_source: DataSource; simulated: boolean; slots: string[]; stops: StripStop[]; model: string | null
}
export interface UpcomingVehicle {
  route_id: string; route: string; mode: string; direction: number; to: string; eta_min: number
  vehicle_id: string; trip_id: string; level: Level | null; load_factor: number | null; stale: boolean | null
}
export interface StopOccupancy { stop_id: string; name: string; now: string; data_source: DataSource; simulated: boolean; vehicles: UpcomingVehicle[] }
export interface WaitOrGo { suggestion: string; vehicles: { eta_min: number; level: Level | null; load_factor: number | null }[]; data_source: DataSource; simulated: boolean }
export interface Leg {
  kind: 'ride' | 'walk'; mode?: string; route?: string; route_id?: string; from: string; to: string
  board_at?: string; alight_at?: string; wait_min?: number; minutes: number; stops?: number; level?: Level; levels?: Level[]; vehicle_id?: string
  from_stop?: string; to_stop?: string; km?: number; fare?: number; path?: [number, number][]
}
export interface Itinerary { legs: Leg[]; total_min: number; transfers: number; worst_level: Level; crowd_score: number; walk_min: number; arrive_at: string; labels: string[] }
export interface Plan { itineraries: Itinerary[]; message?: string; data_source: DataSource; simulated: boolean; from: string; to: string }
export type RankKey = 'crowd' | 'eta' | 'cost' | 'walk' | 'transfers'
export type Mode = 'bus' | 'mrts' | 'metro'
export interface PlanFilters {
  modes: Mode[]; max_walk_min: number | null; max_fare: number | null; max_transfers: number | null
  step_free: boolean; women: boolean; access_walk_min?: number
}
export interface WinItinerary {
  legs: Leg[]; total_min: number; transfers: number; worst_level: Level; crowd_score: number; walk_min: number
  arrive_at: string; fare: number; notes: string[]; rank: number; score: number; best_overall?: boolean
}
export interface WinSlot { depart_at: string; itineraries: WinItinerary[]; filtered_out: number }
export interface WindowPlan {
  from: string; to: string; center: string; window_min: number; rank_by: RankKey[]; slots: WinSlot[]
  data_source: DataSource; simulated: boolean
}
export interface NearStop { stop_id: string; name: string; mode: string; station_id: string; lat: number; lon: number; distance_m: number; walk_min: number }

export interface VehicleInfo {
  vehicle_id: string; route: string; route_id: string; direction: number; last_stop: string; last_report: string
  load: number | null; capacity: number; load_factor: number | null; level: Level | null
  next_stops: { stop_id: string; name: string; eta_min: number; level: Level | null; load_factor: number | null }[]
  data_source: DataSource; simulated: boolean
}

export interface Fetched<T> { data: T | null; error: string | null; loading: boolean; staleSince: Date | null; reload: () => void }

const CACHE_PREFIX = 'kt-cache:'

function remember(url: string, data: unknown) {
  try { localStorage.setItem(CACHE_PREFIX + url, JSON.stringify({ t: Date.now(), data })) } catch { /* storage may be unavailable */ }
}
function recall<T>(url: string): { t: number; data: T } | null {
  try { const s = localStorage.getItem(CACHE_PREFIX + url); return s ? JSON.parse(s) : null } catch { return null }
}

export async function getJSON<T>(path: string, init?: RequestInit): Promise<{ data: T; servedAt: Date; fromCache: boolean }> {
  const res = await fetch(API + path, { ...init, headers: { Accept: 'application/json', ...(init?.headers || {}) } })
  if (!res.ok) {
    let msg = `${res.status}`
    try { const j = await res.json(); msg = j.detail || msg } catch { /* not json */ }
    throw new Error(msg)
  }
  const data = (await res.json()) as T
  const date = res.headers.get('date')
  return { data, servedAt: date ? new Date(date) : new Date(), fromCache: res.headers.get('x-from-cache') === '1' }
}

export function postJSON<T>(path: string, body: unknown) {
  return getJSON<T>(path, { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } })
}

/** Fetch `path`, re-poll every `intervalMs` while visible, back off on errors, use cache offline. */
export function usePolling<T>(path: string | null, intervalMs = 30000): Fetched<T> {
  const cached = path ? recall<T>(path) : null
  const [data, setData] = useState<T | null>(cached?.data ?? null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(!!path)
  const [staleSince, setStale] = useState<Date | null>(null)
  const [tick, setTick] = useState(0)
  const failures = useRef(0)

  useEffect(() => {
    if (!path) return
    let alive = true
    let timer: number | undefined
    let first = true
    const c = recall<T>(path)
    if (c) {
      setData(c.data)
      // until a fresh response arrives, cached data older than 2 minutes shows its age
      if (Date.now() - c.t > 120000) setStale(new Date(c.t))
    }
    const load = async () => {
      // poll only while visible, but always make the first request
      if (!first && document.visibilityState === 'hidden') { schedule(intervalMs); return }
      first = false
      try {
        const { data: d, servedAt, fromCache } = await getJSON<T>(path)
        if (!alive) return
        failures.current = fromCache ? failures.current + 1 : 0
        setData(d); setError(null)
        if (!fromCache) remember(path, d)
        // Served by the service worker from cache (offline), or an unexpectedly old response
        setStale(fromCache || Date.now() - servedAt.getTime() > 120000 ? servedAt : null)
      } catch (e) {
        if (!alive) return
        failures.current += 1
        setError(String((e as Error).message || e))
        const c2 = recall<T>(path)
        if (c2) { setData(c2.data); setStale(new Date(c2.t)) }
      } finally {
        if (alive) setLoading(false)
        schedule(Math.min(intervalMs * 2 ** failures.current, 5 * 60000))
      }
    }
    const schedule = (ms: number) => { if (alive) timer = window.setTimeout(load, ms) }
    const onVis = () => { if (document.visibilityState === 'visible') { window.clearTimeout(timer); load() } }
    document.addEventListener('visibilitychange', onVis)
    setLoading(true)
    load()
    return () => { alive = false; window.clearTimeout(timer); document.removeEventListener('visibilitychange', onVis) }
  }, [path, intervalMs, tick])

  return { data, error, loading, staleSince, reload: () => setTick((t) => t + 1) }
}

export const pct = (lf: number | null | undefined) => (lf == null ? '–' : `${Math.round(lf * 100)}%`)
export const hhmm = (iso: string | Date) =>
  new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' })
export const levelOf = (lf: number | null | undefined): Level | null =>
  lf == null ? null : lf < 0.4 ? 'LOW' : lf < 0.75 ? 'MEDIUM' : lf < 1 ? 'HIGH' : 'CROWDED'
