// Minimal history router (no dependency): path + query string, pushState navigation.
import { useEffect, useState } from 'react'

export function navigate(to: string) {
  if (to === location.pathname + location.search) return
  history.pushState(null, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.scrollTo(0, 0)
}

export function useLocation() {
  const [loc, setLoc] = useState({ path: location.pathname, search: location.search })
  useEffect(() => {
    const on = () => setLoc({ path: location.pathname, search: location.search })
    window.addEventListener('popstate', on)
    return () => window.removeEventListener('popstate', on)
  }, [])
  return { ...loc, params: new URLSearchParams(loc.search) }
}

export function Link(props: React.AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  const { to, onClick, ...rest } = props
  return (
    <a
      href={to}
      onClick={(e) => {
        onClick?.(e)
        if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.button !== 0) return
        e.preventDefault()
        navigate(to)
      }}
      {...rest}
    />
  )
}
