import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import styles from './AppLayout.module.css'

export default function AppLayout() {
  const [navOpen, setNavOpen] = useState(false)
  const location = useLocation()

  // On mobile the sidebar is an overlay drawer, so navigating away from it
  // (tapping a journal, an entry, the bin) has to dismiss it.
  useEffect(() => {
    setNavOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!navOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setNavOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navOpen])

  return (
    <div className={styles.shell}>
      <header className={styles.mobileBar}>
        <button
          type="button"
          className={styles.navToggle}
          onClick={() => setNavOpen((open) => !open)}
          aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
          aria-expanded={navOpen}
        >
          <span className={styles.navToggleIcon} aria-hidden="true" />
        </button>
        <span className={styles.mobileBrand}>CodexJ</span>
      </header>

      <div
        className={`${styles.backdrop} ${navOpen ? styles.backdropOpen : ''}`}
        onClick={() => setNavOpen(false)}
        aria-hidden="true"
      />

      <Sidebar mobileOpen={navOpen} />

      <main className={styles.content}>
        <Outlet />
      </main>
    </div>
  )
}
