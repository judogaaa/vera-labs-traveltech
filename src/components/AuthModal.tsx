import { useEffect, useId, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { Button } from './Button'
import { Input } from './Input'
import { Checkbox } from './Checkbox'
import { IconButton } from './IconButton'
import * as authService from '../services/authService'
import { useFlow } from '../context/FlowContext'
import { useMotionProfile } from '../motion/useMotionProfile'
import {
  modalBackdropTransition,
  modalPanelAnimate,
  modalPanelExit,
  modalPanelInitial,
  modalPanelTransition,
  springs,
} from '../motion/tokens'

type Mode = 'login' | 'register' | 'forgot'

export function AuthModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const titleId = useId()
  const firstFieldRef = useRef<HTMLInputElement>(null)
  const profile = useMotionProfile()
  const { setSession, pushToast } = useFlow()
  const [mode, setMode] = useState<Mode>('login')
  const [loading, setLoading] = useState(false)
  const [agreed, setAgreed] = useState(false)
  const [forgotSent, setForgotSent] = useState(false)
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    confirm: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!open) return
    setMode('login')
    setErrors({})
    setForgotSent(false)
    setLoading(false)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const t = window.setTimeout(() => firstFieldRef.current?.focus(), 50)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = prevOverflow
      window.clearTimeout(t)
      window.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  const validate = () => {
    const next: Record<string, string> = {}
    if (!form.email.includes('@')) next.email = 'Укажите корректный email'
    if (mode !== 'forgot' && form.password.length < 6) next.password = 'Минимум 6 символов'
    if (mode === 'register') {
      if (!form.name.trim()) next.name = 'Укажите имя'
      if (form.confirm !== form.password) next.confirm = 'Пароли не совпадают'
      if (!agreed) next.agreed = 'Нужно согласие'
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const canSubmit =
    mode === 'forgot'
      ? form.email.includes('@')
      : mode === 'login'
        ? form.email.includes('@') && form.password.length >= 6
        : form.name.trim() &&
          form.email.includes('@') &&
          form.password.length >= 6 &&
          form.confirm === form.password &&
          agreed

  const submit = async () => {
    if (!validate()) return
    setLoading(true)
    try {
      if (mode === 'forgot') {
        await authService.requestPasswordReset(form.email)
        setForgotSent(true)
        pushToast('Ссылка для восстановления отправлена')
        return
      }
      if (mode === 'login') {
        const session = await authService.login(form.email, form.password)
        setSession(session)
        pushToast('Вы вошли в аккаунт')
        onClose()
        return
      }
      const session = await authService.register({
        name: form.name,
        email: form.email,
        password: form.password,
      })
      setSession(session)
      pushToast('Аккаунт создан')
      onClose()
    } catch (err) {
      setErrors({ form: err instanceof Error ? err.message : 'Не удалось выполнить действие' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      {open ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
        >
          <motion.button
            type="button"
            className="absolute inset-0 bg-black/35 backdrop-blur-[2px]"
            aria-label="Закрыть"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={modalBackdropTransition(profile)}
          />
          <motion.div
            className={`relative z-10 w-full max-w-md border border-border bg-white p-5 shadow-[0_16px_48px_rgba(14,23,77,0.12)] sm:rounded-[24px] sm:p-6 ${
              profile.compact ? 'rounded-t-[24px] pb-[max(1.25rem,env(safe-area-inset-bottom))]' : 'rounded-[24px]'
            }`}
            initial={modalPanelInitial(profile)}
            animate={modalPanelAnimate(profile)}
            exit={modalPanelExit(profile)}
            transition={modalPanelTransition(profile)}
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 id={titleId} className="text-xl font-bold text-brand-blue-950">
                  {mode === 'forgot' ? 'Восстановление пароля' : 'Войти или зарегистрироваться'}
                </h2>
                {mode !== 'forgot' ? (
                  <div className="mt-3 flex gap-2">
                    {(['login', 'register'] as const).map((tab) => (
                      <motion.button
                        key={tab}
                        type="button"
                        layout
                        className={`rounded-full px-3 py-1.5 text-sm font-semibold ${
                          mode === tab
                            ? 'bg-brand-blue-950 text-white'
                            : 'bg-surface-muted text-text-secondary'
                        }`}
                        transition={profile.reduce ? { duration: 0.12 } : springs.snappy}
                        onClick={() => setMode(tab)}
                      >
                        {tab === 'login' ? 'Войти' : 'Регистрация'}
                      </motion.button>
                    ))}
                  </div>
                ) : null}
              </div>
              <IconButton label="Закрыть" onClick={onClose}>
                <X size={18} />
              </IconButton>
            </div>

            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={mode}
                className="space-y-3"
                initial={profile.reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={profile.reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
                transition={profile.reduce ? { duration: 0.12 } : springs.snappy}
              >
                {mode === 'register' ? (
                  <Input
                    ref={firstFieldRef}
                    label="Имя"
                    name="name"
                    autoComplete="name"
                    value={form.name}
                    error={errors.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                  />
                ) : null}
                <Input
                  ref={mode === 'register' ? undefined : firstFieldRef}
                  label="Email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  value={form.email}
                  error={errors.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
                {mode !== 'forgot' ? (
                  <Input
                    label="Пароль"
                    name="password"
                    type="password"
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    value={form.password}
                    error={errors.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                  />
                ) : null}
                {mode === 'register' ? (
                  <Input
                    label="Повторите пароль"
                    name="confirm"
                    type="password"
                    autoComplete="new-password"
                    value={form.confirm}
                    error={errors.confirm}
                    onChange={(e) => setForm({ ...form, confirm: e.target.value })}
                  />
                ) : null}
                {mode === 'register' ? (
                  <Checkbox
                    label="Я согласен с условиями использования сервиса"
                    checked={agreed}
                    onChange={(e) => setAgreed(e.target.checked)}
                  />
                ) : null}
                {errors.agreed ? <p className="text-sm text-error">{errors.agreed}</p> : null}
                {errors.form ? <p className="text-sm text-error">{errors.form}</p> : null}
                {forgotSent ? (
                  <p className="rounded-2xl bg-success-soft px-3 py-2 text-sm text-success">
                    Если аккаунт существует, мы отправили ссылку на почту.
                  </p>
                ) : null}
              </motion.div>
            </AnimatePresence>

            <div className="mt-5 space-y-3">
              <Button fullWidth disabled={!canSubmit || loading} onClick={() => void submit()}>
                {loading
                  ? 'Подождите…'
                  : mode === 'login'
                    ? 'Войти'
                    : mode === 'register'
                      ? 'Создать аккаунт'
                      : 'Отправить ссылку'}
              </Button>
              {mode === 'login' ? (
                <button
                  type="button"
                  className="w-full text-sm font-medium text-brand-blue-800"
                  onClick={() => setMode('forgot')}
                >
                  Забыли пароль?
                </button>
              ) : null}
              {mode === 'forgot' ? (
                <button
                  type="button"
                  className="w-full text-sm font-medium text-brand-blue-800"
                  onClick={() => setMode('login')}
                >
                  Назад ко входу
                </button>
              ) : null}
            </div>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  )
}
