// After a deploy, a page served from the old service-worker shell may ask for a lazy chunk that no
// longer exists. Reload once to pick up the new shell instead of showing a broken view.
import { lazy, type ComponentType } from 'react'

export function lazyReload<T extends ComponentType<any>>(load: () => Promise<{ default: T }>) {
  return lazy(() =>
    load()
      .then((m) => { try { sessionStorage.removeItem('kt-chunk-reload') } catch { /* ignore */ } return m })
      .catch((e) => {
        let reloaded = false
        try { reloaded = !!sessionStorage.getItem('kt-chunk-reload'); sessionStorage.setItem('kt-chunk-reload', '1') } catch { /* ignore */ }
        if (!reloaded) window.location.reload()
        throw e
      }),
  )
}
