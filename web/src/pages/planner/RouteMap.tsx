// Map of one chosen itinerary, loaded only when a route is selected. Each ride segment is coloured by
// its forecast crowd level; walking legs are dashed. Text in RouteDetail carries the same information.
import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { WinItinerary } from '../../api'
import { useT } from '../../i18n'

const COLORS: Record<string, string> = { LOW: '#7fbf3a', MEDIUM: '#ebc247', HIGH: '#f08a3c', CROWDED: '#ba1a1a' }

export default function RouteMap({ it }: { it: WinItinerary }) {
  const t = useT()
  const ref = useRef<HTMLDivElement>(null)
  const [offline, setOffline] = useState(typeof navigator !== 'undefined' && !navigator.onLine)

  useEffect(() => {
    if (!ref.current || offline) return
    const features: GeoJSON.Feature[] = []
    const b = new maplibregl.LngLatBounds()
    it.legs.forEach((l) => {
      const p = l.path ?? []
      p.forEach((xy) => b.extend(xy))
      if (l.kind === 'walk') {
        if (p.length > 1) features.push({ type: 'Feature', properties: { kind: 'walk' }, geometry: { type: 'LineString', coordinates: p } })
        return
      }
      for (let i = 0; i + 1 < p.length; i++) {
        const lvl = l.levels?.[i] ?? l.level ?? 'LOW'
        features.push({ type: 'Feature', properties: { kind: 'ride', color: COLORS[lvl] }, geometry: { type: 'LineString', coordinates: [p[i], p[i + 1]] } })
      }
    })
    if (b.isEmpty()) return
    const map = new maplibregl.Map({
      container: ref.current,
      style: {
        version: 8,
        sources: { osm: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, attribution: '© OpenStreetMap contributors' } },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      bounds: b, fitBoundsOptions: { padding: 36 },
    })
    map.on('error', () => setOffline(!navigator.onLine))
    map.on('load', () => {
      map.addSource('route', { type: 'geojson', data: { type: 'FeatureCollection', features } })
      map.addLayer({ id: 'casing', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'ride'],
        paint: { 'line-color': '#ffffff', 'line-width': 9 }, layout: { 'line-cap': 'round', 'line-join': 'round' } })
      map.addLayer({ id: 'ride', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'ride'],
        paint: { 'line-color': ['get', 'color'], 'line-width': 6 }, layout: { 'line-cap': 'round', 'line-join': 'round' } })
      map.addLayer({ id: 'walk', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'walk'],
        paint: { 'line-color': '#44474e', 'line-width': 3, 'line-dasharray': [1.5, 1.5] } })
    })
    const rides = it.legs.filter((l) => l.kind === 'ride' && l.path?.length)
    const pins: [[number, number], string, string][] = []
    rides.forEach((l, i) => pins.push([l.path![0], i === 0 ? '#3e6a00' : '#465f88', `${i === 0 ? '▶' : '⇄'} ${l.route} · ${l.from}`]))
    if (rides.length) { const last = rides[rides.length - 1]; pins.push([last.path![last.path!.length - 1], '#002046', `■ ${last.to}`]) }
    pins.forEach(([xy, bg, label]) => {
      const el = document.createElement('div')
      el.style.cssText = `width:16px;height:16px;border-radius:50%;border:3px solid #fff;box-shadow:0 1px 4px rgba(0,32,70,.5);background:${bg}`
      el.setAttribute('aria-label', label)
      new maplibregl.Marker({ element: el }).setLngLat(xy).setPopup(new maplibregl.Popup({ offset: 12 }).setText(label)).addTo(map)
    })
    return () => map.remove()
  }, [it, offline])

  if (offline) return <p className="card p-4 text-sm text-slate-600 dark:text-slate-400" role="status">{t('mapOffline')}</p>
  return <div ref={ref} className="card h-80 w-full overflow-hidden" role="region" aria-label={t('routeMap')} />
}
