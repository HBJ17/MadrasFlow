// Light / dark theme: the `dark` class on <html> (set before first paint in index.html).
// A saved choice wins; with none saved the app follows the device setting.
import { useEffect, useState } from 'react'

const KEY = 'kt-theme'
const isDark = () => document.documentElement.classList.contains('dark')

export function setDark(dark: boolean) {
  document.documentElement.classList.toggle('dark', dark)
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', dark ? '#12141a' : '#fdf9f1')
  try { localStorage.setItem(KEY, dark ? 'dark' : 'light') } catch { /* storage may be unavailable */ }
}

// Re-renders when the theme changes, from the toggle or from the device setting.
export function useDark() {
  const [dark, set] = useState(isDark)
  useEffect(() => {
    const obs = new MutationObserver(() => set(isDark()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    const mq = matchMedia('(prefers-color-scheme: dark)')
    const onSystem = (e: MediaQueryListEvent) => {
      let saved: string | null = null
      try { saved = localStorage.getItem(KEY) } catch { /* ignore */ }
      if (!saved) document.documentElement.classList.toggle('dark', e.matches)
    }
    mq.addEventListener('change', onSystem)
    return () => { obs.disconnect(); mq.removeEventListener('change', onSystem) }
  }, [])
  return dark
}
