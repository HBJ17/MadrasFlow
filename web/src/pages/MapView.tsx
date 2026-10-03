// Loaded only when the user taps "Show map" (low-bandwidth default is text + colour).
import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { usePolling, type Level, type StopInfo } from '../api'

const COLORS: Record<string, string> = { LOW: '#15803d', MEDIUM: '#facc15', HIGH: '#fb923c', CROWDED: '#b91c1c' }

export default function MapView({ stops }: { stops: { id: string; name: string; level: Level | null }[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const all = usePolling<StopInfo[]>('/stops', 3600_000)
  useEffect(() => {
    if (!ref.current || !all.data) return
    const byId = new Map(all.data.map((s) => [s.stop_id, s]))
    const pts = stops.map((s) => ({ ...s, g: byId.get(s.id) })).filter((s) => s.g)
    if (!pts.length) return
    const map = new maplibregl.Map({
      container: ref.current,
      style: {
        version: 8,
        sources: { osm: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256,
          attribution: '© OpenStreetMap contributors' } },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      center: [pts[0].g!.lon, pts[0].g!.lat],
      zoom: 12,
    })
    const b = new maplibregl.LngLatBounds()
    pts.forEach((p) => {
      const el = document.createElement('div')
      el.style.cssText = `width:14px;height:14px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 2px #000;background:${COLORS[p.level ?? ''] ?? '#94a3b8'}`
      el.setAttribute('aria-label', `${p.name}: ${p.level ?? 'no forecast'}`)
      new maplibregl.Marker({ element: el }).setLngLat([p.g!.lon, p.g!.lat]).setPopup(new maplibregl.Popup().setText(`${p.name} — ${p.level ?? '–'}`)).addTo(map)
      b.extend([p.g!.lon, p.g!.lat])
    })
    map.fitBounds(b, { padding: 30, duration: 0 })
    return () => map.remove()
  }, [stops, all.data])
  return <div ref={ref} className="card h-96 w-full overflow-hidden" role="region" aria-label="Map of stops coloured by crowd level" />
}
