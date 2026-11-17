import { motion } from 'framer-motion'
import { Check, Circle, Loader2 } from 'lucide-react'
import { useMotionProfile } from '../../../motion/useMotionProfile'
import { springs } from '../../../motion/tokens'

export type ProgressStep = {
  id: string
  label: string
  status: 'pending' | 'active' | 'done' | 'error'
}

type Props = {
  steps: ProgressStep[]
  title?: string
}

export function ProgressSteps({ steps, title = 'Исследование' }: Props) {
  const profile = useMotionProfile()

  return (
    <section
      className="rounded-2xl border border-border bg-white p-4 shadow-sm sm:p-5"
      aria-live="polite"
      aria-busy={steps.some((s) => s.status === 'active')}
    >
      <h3 className="text-sm font-bold text-brand-blue-950">{title}</h3>
      <ol className="mt-3 flex flex-col gap-2.5">
        {steps.map((step, index) => {
          const Icon =
            step.status === 'done'
              ? Check
              : step.status === 'active'
                ? Loader2
                : Circle
          return (
            <motion.li
              key={step.id}
              className="flex items-center gap-3 text-sm"
              initial={profile.reduce ? false : { opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={
                profile.reduce ? { duration: 0 } : { ...springs.snappy, delay: 0.04 * index }
              }
            >
              <span
                className={[
                  'flex h-7 w-7 shrink-0 items-center justify-center rounded-full border',
                  step.status === 'done'
                    ? 'border-brand-green-400 bg-brand-green-100 text-brand-blue-950'
                    : step.status === 'active'
                      ? 'border-brand-blue-800 bg-brand-blue-950 text-white'
                      : step.status === 'error'
                        ? 'border-error bg-error-bg text-error'
                        : 'border-border bg-surface-soft text-text-muted',
                ].join(' ')}
                aria-hidden
              >
                <Icon
                  size={14}
                  className={step.status === 'active' && !profile.reduce ? 'animate-spin' : ''}
                />
              </span>
              <span
                className={
                  step.status === 'active'
                    ? 'font-semibold text-brand-blue-950'
                    : step.status === 'done'
                      ? 'text-text-primary'
                      : 'text-text-muted'
                }
              >
                {step.label}
              </span>
            </motion.li>
          )
        })}
      </ol>
    </section>
  )
}
