// "Check Rapido" first/last-mile hand-off: opens Rapido's mobile web app with one end of the ride filled in
// (drop = where the trip starts, or pickup = where it ends) and the other left blank for the user.
// Uses the undocumented route Rapido's own SEO route pages use (unup-home/seo/:pickup/:drop?version=v3);
// Rapido geocodes each "Place,City" text and picks the first match. See KNOWN_LIMITS.md.
import type { Leg } from './api'

const BLANK = '    '   // 4 spaces: long enough to pass Rapido's length check, matches nothing, so the field stays empty

// Make a stop name specific enough for Rapido's place search ("Taramani" → "Taramani MRTS Station").
function placeName(name: string, mode?: string): string {
  if (/station|stop|stand|terminus|depot/i.test(name)) return name
  if (mode === 'mrts') return `${name} MRTS Station`
  if (mode === 'metro') return `${name} Metro Station`
  if (mode === 'bus') return `${name} Bus Stop`
  return name
}

function rapidoUrl(from: string | null, to: string | null, city = 'Chennai'): string {
  const seg = (s: string | null) => encodeURIComponent(s ? `${s.replace(/[,/]/g, ' ').trim()},${city}` : BLANK)
  return `https://m.rapido.bike/unup-home/seo/${seg(from)}/${seg(to)}?version=v3`
}

// Ride to the trip's first stop (drop filled, pickup blank).
export function rapidoToStart(legs: Leg[]): { place: string; url: string } {
  const ride = legs.find((x) => x.kind === 'ride')
  const place = placeName(legs[0].from, ride?.mode)
  return { place: legs[0].from, url: rapidoUrl(null, place) }
}

// Ride onward from the trip's last stop (pickup filled, drop blank).
export function rapidoFromEnd(legs: Leg[]): { place: string; url: string } {
  const ride = [...legs].reverse().find((x) => x.kind === 'ride')
  const last = legs[legs.length - 1]
  return { place: last.to, url: rapidoUrl(placeName(last.to, ride?.mode), null) }
}
