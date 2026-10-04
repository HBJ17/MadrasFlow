// Operator dashboard: fleet heatmap, recommendations, what-if simulator (digital twin).
import { usePolling, type RouteInfo } from '../api'
import Advisories from './depot/Advisories'
import Heatmap from './depot/Heatmap'
import ScenarioBuilder from './depot/ScenarioBuilder'

export default function Depot() {
  const routes = usePolling<RouteInfo[]>('/routes', 3600_000)
  const r = routes.data ?? []
  return (
    <div className="space-y-4">
      <h1 className="text-[28px] font-bold leading-tight text-[#002046] sm:text-[32px] dark:text-navy-soft">Depot dashboard</h1>
      <Heatmap />
      <Advisories />
      <ScenarioBuilder routes={r} />
    </div>
  )
}
