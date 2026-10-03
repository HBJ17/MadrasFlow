// Small shared pieces for the depot dashboard.
export function Panel({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="card space-y-3 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-3 dark:border-white/5"><h2 className="text-lg font-semibold text-[#002046] dark:text-navy-soft">{title}</h2>{right}</div>
      {children}
    </section>
  )
}

// SVG presentation attributes cannot use CSS variables, so pick the chart palette from the colour scheme.
export const DARK = typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
export const CHART = DARK ? { before: '#9a9ca5', after: '#b9f477', grid: '#2d3341' } : { before: '#9a9ca5', after: '#002046', grid: '#e2ded5' }
