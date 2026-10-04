// Small shared pieces for the depot dashboard.
import { useDark } from '../../theme'

export function Panel({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="card space-y-3 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-3 dark:border-white/5"><h2 className="text-lg font-semibold text-[#002046] dark:text-navy-soft">{title}</h2>{right}</div>
      {children}
    </section>
  )
}

// SVG presentation attributes cannot use CSS variables, so pick the chart palette from the current theme.
export function useChartColors() {
  return useDark() ? { before: '#9a9ca5', after: '#b9f477', grid: '#2d3341' } : { before: '#9a9ca5', after: '#002046', grid: '#e2ded5' }
}

// Twin-tested effect of the accepted advisories (GET /fleet/effect), shared by the heatmap and the cards.
export interface EffectStatus {
  status: 'none' | 'computing' | 'ready' | 'error'; accepted: number[]; error: string | null
  summary: null | {
    computed_at: string; cells: number; skipped: number[]; trips_added: number | null
    left_behind_total: { before: number; after: number }; crowded_vehicle_stops: { before: number; after: number }
    unmet_demand: { before: number; after: number }
    per_advisory: { advisory_id: number; lf_before?: number | null; lf_after?: number | null; skipped?: boolean }[]
  }
}
// Fired after Accept / Undo so both panels refresh at once instead of waiting for the next poll.
export const ACCEPTED_EVENT = 'mf-accepted-changed'
