// Small shared pieces for the depot dashboard.
export function Panel({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="card space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">{title}</h2>{right}</div>
      {children}
    </section>
  )
}

// SVG presentation attributes cannot use CSS variables, so pick the chart palette from the colour scheme.
export const DARK = typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
export const CHART = DARK ? { before: '#94a3b8', after: '#2dd4bf', grid: '#334155' } : { before: '#64748b', after: '#0d9488', grid: '#e2e8f0' }
