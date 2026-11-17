import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { Logo } from './Logo'
import { Button } from './Button'
import { IconButton } from './IconButton'
import { AuthModal } from './AuthModal'
import { useFlow } from '../context/FlowContext'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

/** Product — always visible so the bar explains what the app does. */
const productLinks = [
  { to: '/catalog', label: 'Каталог' },
  { to: '/oh-route', label: 'О!Маршрут' },
  { to: '/hotel-intelligence', label: 'О!Подбор' },
  { to: '/#how', label: 'Как это работает' },
]

/** Personal — right side when signed in; not duplicated in product nav. */
const personalLinks = [
  { to: '/favorites', label: 'Избранное' },
  { to: '/trips', label: 'Мои поездки' },
]

function navClass({ isActive }: { isActive: boolean }) {
  return [
    'px-1 py-1 text-[15px] no-underline transition-colors duration-150',
    isActive
      ? 'font-semibold text-brand-blue-950'
      : 'font-medium text-text-secondary hover:text-brand-blue-950',
  ].join(' ')
}

function personalClass({ isActive }: { isActive: boolean }) {
  return [
    'px-1 py-1 text-[14px] no-underline transition-colors duration-150',
    isActive
      ? 'font-semibold text-brand-blue-950'
      : 'font-medium text-text-muted hover:text-brand-blue-950',
  ].join(' ')
}

export function Header() {
  const [open, setOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const location = useLocation()
  const profile = useMotionProfile()
  const { session, logout, authOpen, setAuthOpen, pushToast } = useFlow()

  useEffect(() => {
    setOpen(false)
    setMenuOpen(false)
  }, [location.pathname, location.hash])

  useEffect(() => {
    if (!menuOpen) return
    const onClick = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false)
    }
    window.addEventListener('mousedown', onClick)
    return () => window.removeEventListener('mousedown', onClick)
  }, [menuOpen])

  const initials = session?.user.name?.trim()?.charAt(0)?.toUpperCase() ?? 'О'
  const menuTransition = profile.reduce ? { duration: 0.12 } : springs.snappy
  const sheetTransition = profile.reduce ? { duration: 0.12 } : springs.sheet

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-border/80 bg-white/90 backdrop-blur-md">
        <div className="page-container flex h-14 items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-7">
            <Logo />
            <nav className="hidden items-center gap-5 lg:flex" aria-label="Основная навигация">
              {productLinks.map((link) =>
                link.to.includes('#') ? (
                  <Link
                    key={link.to}
                    to={link.to}
                    className="px-1 py-1 text-[15px] font-medium text-text-secondary no-underline transition-colors duration-150 hover:text-brand-blue-950"
                  >
                    {link.label}
                  </Link>
                ) : (
                  <NavLink key={link.to} to={link.to} className={navClass}>
                    {link.label}
                  </NavLink>
                ),
              )}
            </nav>
          </div>

          <div className="hidden items-center gap-5 lg:flex">
            {session ? (
              <>
                <nav className="flex items-center gap-4" aria-label="Личное">
                  {personalLinks.map((link) => (
                    <NavLink key={link.to} to={link.to} className={personalClass}>
                      {link.label}
                    </NavLink>
                  ))}
                </nav>
                <div className="relative" ref={menuRef}>
                  <motion.button
                    type="button"
                    className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-blue-950 text-sm font-semibold text-white"
                    onClick={() => setMenuOpen((v) => !v)}
                    aria-expanded={menuOpen}
                    aria-haspopup="menu"
                    aria-label={`Аккаунт: ${session.user.name}`}
                    whileTap={profile.reduce ? undefined : { scale: 0.94 }}
                    transition={springs.tap}
                  >
                    {initials}
                  </motion.button>
                  <AnimatePresence>
                    {menuOpen ? (
                      <motion.div
                        role="menu"
                        className="absolute right-0 mt-2 w-52 origin-top-right overflow-hidden rounded-xl border border-border bg-white py-1 shadow-[0_12px_32px_rgba(14,23,77,0.1)]"
                        initial={profile.reduce ? { opacity: 0 } : { opacity: 0, y: 6, scale: 0.96 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={profile.reduce ? { opacity: 0 } : { opacity: 0, y: 4, scale: 0.98 }}
                        transition={menuTransition}
                      >
                        <div className="border-b border-border px-3.5 py-2.5">
                          <p className="truncate text-sm font-medium text-text-primary">{session.user.name}</p>
                          <p className="truncate text-xs text-text-muted">{session.user.email}</p>
                        </div>
                        <button
                          type="button"
                          role="menuitem"
                          className="block w-full px-3.5 py-2.5 text-left text-sm text-text-primary transition-colors hover:bg-brand-green-100"
                          onClick={() => {
                            setMenuOpen(false)
                            pushToast(`${session.user.name} · ${session.user.email}`)
                          }}
                        >
                          Профиль
                        </button>
                        <button
                          type="button"
                          role="menuitem"
                          className="block w-full px-3.5 py-2.5 text-left text-sm text-error transition-colors hover:bg-error-bg"
                          onClick={() => {
                            setMenuOpen(false)
                            logout()
                          }}
                        >
                          Выйти
                        </button>
                      </motion.div>
                    ) : null}
                  </AnimatePresence>
                </div>
              </>
            ) : (
              <button
                type="button"
                className="text-[15px] font-medium text-brand-blue-950 transition-opacity hover:opacity-75"
                onClick={() => setAuthOpen(true)}
              >
                Войти
              </button>
            )}
          </div>

          <div className="lg:hidden">
            <IconButton label={open ? 'Закрыть меню' : 'Открыть меню'} onClick={() => setOpen((v) => !v)}>
              {open ? <X size={20} /> : <Menu size={20} />}
            </IconButton>
          </div>
        </div>

        <AnimatePresence initial={false}>
          {open ? (
            <motion.div
              className="overflow-hidden border-t border-border bg-white lg:hidden"
              initial={profile.reduce ? { height: 0, opacity: 0 } : { height: 0, opacity: 0.85 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={sheetTransition}
            >
              <nav className="flex flex-col gap-0.5 px-4 py-3" aria-label="Мобильное меню">
                {productLinks.map((link, i) => (
                  <motion.div
                    key={link.to}
                    initial={profile.reduce ? false : { opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={profile.reduce ? { duration: 0 } : { ...springs.snappy, delay: 0.03 * i }}
                  >
                    <Link
                      to={link.to}
                      className="block rounded-lg px-3 py-2.5 text-[15px] font-medium text-brand-blue-950 no-underline hover:bg-brand-green-100"
                    >
                      {link.label}
                    </Link>
                  </motion.div>
                ))}
                {session ? (
                  <>
                    <div className="my-1 border-t border-border" />
                    {personalLinks.map((link) => (
                      <Link
                        key={link.to}
                        to={link.to}
                        className="rounded-lg px-3 py-2.5 text-[15px] font-medium text-text-secondary no-underline hover:bg-brand-green-100 hover:text-brand-blue-950"
                      >
                        {link.label}
                      </Link>
                    ))}
                    <Button
                      fullWidth
                      variant="secondary"
                      className="mt-2"
                      onClick={() => {
                        logout()
                        setOpen(false)
                      }}
                    >
                      Выйти
                    </Button>
                  </>
                ) : (
                  <Button fullWidth variant="secondary" className="mt-2" onClick={() => setAuthOpen(true)}>
                    Войти
                  </Button>
                )}
              </nav>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </header>
      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
    </>
  )
}
