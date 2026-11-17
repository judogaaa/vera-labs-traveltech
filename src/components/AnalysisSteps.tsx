import { AnimatePresence, motion } from 'framer-motion'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

const defaultSteps = [
  'Готовим изображение',
  'Считываем визуальные признаки',
  'Сравниваем с каталогом',
  'Отбираем лучшие совпадения',
]

export function AnalysisSteps({
  activeStep,
  labels = defaultSteps,
}: {
  activeStep: number
  labels?: string[]
}) {
  const profile = useMotionProfile()
  const currentLabel = labels[Math.min(activeStep, labels.length - 1)] ?? labels[0]

  return (
    <div className="space-y-5">
      <AnimatePresence mode="wait" initial={false}>
        <motion.p
          key={currentLabel}
          className="text-[17px] font-semibold tracking-[-0.02em] text-brand-blue-950"
          initial={profile.reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={profile.reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
          transition={profile.reduce ? { duration: 0.12 } : springs.snappy}
        >
          {currentLabel}
        </motion.p>
      </AnimatePresence>

      <ol className="flex flex-col gap-2.5" aria-label="Этапы анализа">
        {labels.map((label, index) => {
          const done = index < activeStep
          const current = index === activeStep
          return (
            <li key={label} className="flex items-center gap-3">
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                  current
                    ? 'bg-brand-blue-950 text-white'
                    : done
                      ? 'bg-brand-green-400 text-brand-blue-950'
                      : 'bg-surface-muted text-text-muted'
                }`}
                aria-hidden
              >
                {done ? '✓' : index + 1}
              </span>
              <span
                className={`text-[14px] transition-colors duration-300 ${
                  current
                    ? 'font-medium text-text-primary'
                    : done
                      ? 'text-text-secondary'
                      : 'text-text-muted'
                }`}
              >
                {label}
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
