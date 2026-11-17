import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { AnalysisSteps } from '../components/AnalysisSteps'
import { SafeImage } from '../components/SafeImage'
import { Button } from '../components/Button'
import { VibeMoodBoard } from '../components/VibeMoodBoard'
import { useFlow } from '../context/FlowContext'
import { isRegionSearchMode } from '../types/visualSearch'
import {
  analyzeVisualSearchInput,
  findHotelMatches,
  getMatchScenario,
} from '../services/visionService'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

const STEPS_FULL = [
  'Готовим изображение',
  'Считываем визуальные признаки',
  'Сравниваем с каталогом',
  'Отбираем лучшие совпадения',
]

const STEPS_REGION = [
  'Готовим выделенную деталь',
  'Считываем визуальные признаки',
  'Сравниваем с каталогом',
  'Отбираем похожие объекты',
]

type Phase = 'running' | 'error' | 'empty'

export function AnalysisScreen() {
  const navigate = useNavigate()
  const profile = useMotionProfile()
  const { uploaded, visualSearch, setAnalysis, setMatches } = useFlow()
  const [step, setStep] = useState(0)
  const [phase, setPhase] = useState<Phase>('running')
  const [errorMessage, setErrorMessage] = useState('')

  const isRegion = isRegionSearchMode(visualSearch?.mode)
  const steps = isRegion ? STEPS_REGION : STEPS_FULL

  useEffect(() => {
    if (!uploaded || !visualSearch) {
      navigate('/', { replace: true })
      return
    }

    let cancelled = false
    const timeouts: number[] = []

    const run = async () => {
      setPhase('running')
      setErrorMessage('')
      setStep(0)

      try {
        // Soft stage hint only — does not gate the search.
        timeouts.push(
          window.setTimeout(() => {
            if (!cancelled) setStep(1)
          }, 220),
        )

        const analysis = await analyzeVisualSearchInput(visualSearch)
        if (cancelled) return
        setAnalysis(analysis)
        setStep(2)

        const matches = await findHotelMatches(analysis, visualSearch)
        if (cancelled) return
        setMatches(matches)
        setStep(3)

        if (matches.length === 0) {
          setPhase('empty')
          navigate('/search/no-match', { replace: true })
          return
        }

        const scenario = getMatchScenario()
        if (scenario === 'none') {
          navigate('/search/no-match', { replace: true })
        } else if (scenario === 'multiple') {
          navigate('/search/matches', { replace: true })
        } else {
          navigate('/search/result', { replace: true })
        }
      } catch (err) {
        if (cancelled) return
        setPhase('error')
        setErrorMessage(err instanceof Error ? err.message : 'Не удалось проанализировать фото')
      }
    }

    void run()

    return () => {
      cancelled = true
      timeouts.forEach((id) => window.clearTimeout(id))
    }
  }, [uploaded, visualSearch, navigate, setAnalysis, setMatches])

  if (!uploaded || !visualSearch) return null

  const previewSrc =
    isRegion && visualSearch.cropPreviewUrl
      ? visualSearch.cropPreviewUrl
      : visualSearch.originalPreviewUrl

  return (
    <main className="min-h-[calc(100vh-4rem)] bg-gradient-to-b from-[#f4f8ee] via-white to-white">
      <div className="page-container py-8 sm:py-12">
        <div className="mx-auto grid max-w-[980px] items-start gap-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:gap-12">
          <motion.div
            className="relative"
            initial={profile.reduce ? { opacity: 0 } : { opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={profile.reduce ? { duration: 0.15 } : springs.soft}
          >
            <p className="mb-3 text-sm font-medium text-brand-blue-900">Подборка настроения</p>
            <div className="relative overflow-hidden rounded-[28px] border border-border/70 shadow-[0_20px_50px_-28px_rgba(14,23,77,0.35)]">
              <VibeMoodBoard activeStep={step} />

              {/* User photo thumbnail — visible while search runs */}
              <motion.div
                className="absolute bottom-4 right-4 z-10 sm:bottom-5 sm:right-5"
                initial={profile.reduce ? { opacity: 0 } : { opacity: 0, scale: 0.88, y: 8 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                transition={profile.reduce ? { duration: 0.15 } : { ...springs.soft, delay: 0.08 }}
              >
                <div className="overflow-hidden rounded-2xl border-2 border-white/90 bg-white shadow-[0_10px_28px_-10px_rgba(14,23,77,0.55)]">
                  <SafeImage
                    src={previewSrc}
                    alt="Ваше фото"
                    className="h-16 w-16 object-cover sm:h-[4.5rem] sm:w-[4.5rem]"
                    eager
                  />
                </div>
                <p className="mt-1.5 max-w-[4.5rem] truncate text-center text-[10px] font-medium text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.65)] sm:max-w-[5rem]">
                  Ваше фото
                </p>
              </motion.div>
            </div>
          </motion.div>

          <motion.aside
            initial={profile.reduce ? { opacity: 0 } : { opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={profile.reduce ? { duration: 0.15 } : { ...springs.soft, delay: 0.05 }}
            className="lg:pt-2"
          >
            <p className="text-sm font-medium text-brand-blue-900">О!Хочу</p>
            <h1 className="mt-3 text-[30px] font-semibold leading-[1.12] tracking-[-0.03em] text-brand-blue-950 sm:text-[38px]">
              Подбираем отели по вашему фото
            </h1>
            <p className="mt-3 max-w-md text-[15px] leading-6 text-text-secondary">
              Анализируем изображение и ищем наиболее подходящие варианты в нашем каталоге
            </p>

            <div className="mt-8 rounded-[24px] border border-border bg-white/90 p-5 shadow-sm backdrop-blur-sm">
              <AnimatePresence mode="wait" initial={false}>
                {phase === 'error' ? (
                  <motion.div
                    key="error"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="space-y-4"
                  >
                    <p className="text-[15px] font-semibold text-error">Не удалось завершить анализ</p>
                    <p className="text-sm text-text-secondary">{errorMessage}</p>
                    <div className="flex flex-wrap gap-2">
                      <Button onClick={() => navigate('/search/preview')}>Изменить фото</Button>
                      <Button variant="secondary" onClick={() => navigate('/')}>
                        На главную
                      </Button>
                    </div>
                  </motion.div>
                ) : phase === 'empty' ? (
                  <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                    <p className="text-[15px] font-medium text-text-primary">Точных совпадений не найдено</p>
                    <p className="mt-1 text-sm text-text-secondary">Переходим к похожим вариантам…</p>
                  </motion.div>
                ) : (
                  <motion.div key="steps" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                    <AnalysisSteps activeStep={step} labels={steps} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.aside>
        </div>
      </div>
    </main>
  )
}
