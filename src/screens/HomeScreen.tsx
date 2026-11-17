import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion, useInView, useReducedMotion } from 'framer-motion'
import { Building2, CalendarCheck, ImagePlus, Lasso, Plane, Ticket } from 'lucide-react'
import { UploadDropzone } from '../components/UploadDropzone'
import { SafeImage } from '../components/SafeImage'
import { RotatingCityWord } from '../components/RotatingCityWord'
import { useRotatingCityIndex } from '../hooks/useRotatingCity'
import { SHORT_CITIES } from '../data/topCities'
import { useFlow } from '../context/FlowContext'

const steps = [
  {
    step: '1',
    title: 'Загрузите фото',
    text: 'Скриншот из Reels, TikTok, Telegram или галереи.',
    icon: ImagePlus,
  },
  {
    step: '2',
    title: 'Обведите деталь',
    text: 'Выделите вывеску или фасад — или весь кадр.',
    icon: Lasso,
  },
  {
    step: '3',
    title: 'Выберите отель',
    text: 'Точное совпадение или похожие дешевле рядом.',
    icon: Building2,
  },
  {
    step: '4',
    title: 'Забронируйте',
    text: 'Номер, даты, оплата и поездка в одном месте.',
    icon: CalendarCheck,
  },
]

const cities = [
  { name: 'Стамбул', src: '/demo/hotels/rixos/01.jpg' },
  { name: 'Рим', src: '/demo/hotels/akka/01.jpg' },
  { name: 'Барселона', src: '/demo/hotels/nirvana/01.jpg' },
  { name: 'Дубай', src: '/demo/hotels/seven-seas/01.jpg' },
  { name: 'Афины', src: '/demo/hotels/rixos/03.jpg' },
]

type Phase = 'photos' | 'reveal'

/** Boarding-strip destination, synced with the hero title rotation. */
function RouteDestination() {
  const index = useRotatingCityIndex()
  const city = SHORT_CITIES[index].toUpperCase()
  const measRef = useRef<HTMLSpanElement>(null)
  const [w, setW] = useState<number | undefined>(undefined)

  // Fit the box to the current word so the dashed line always touches it.
  // Width animates via CSS transition instead of jumping.
  // +2px guards against sub-pixel rounding (offsetWidth is integer).
  useLayoutEffect(() => {
    if (measRef.current) {
      const next = measRef.current.offsetWidth + 2
      setW((prev) => (prev === next ? prev : next))
    }
  }, [city])

  return (
    <span
      style={w ? { width: w } : undefined}
      className="relative block max-w-[40vw] min-w-0 overflow-hidden text-right transition-[width] duration-300 ease-out sm:max-w-none sm:overflow-visible"
    >
      <span
        ref={measRef}
        aria-hidden
        className="bp-code invisible inline-block whitespace-nowrap text-[24px] leading-none sm:text-[30px]"
      >
        {city}
      </span>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={city}
          className="bp-code absolute inset-0 block truncate text-right text-[24px] leading-none sm:text-[30px]"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.28, ease: 'easeOut' }}
        >
          {city}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}

export function HomeScreen() {
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const { setUploaded, pushToast } = useFlow()
  const [phase, setPhase] = useState<Phase>(reduce ? 'reveal' : 'photos')

  useEffect(() => {
    if (reduce) return
    const t = window.setTimeout(() => setPhase('reveal'), 1800)
    return () => window.clearTimeout(t)
  }, [reduce])

  const showPhotos = phase === 'photos'
  const showCard = phase === 'reveal'

  return (
    <main className="overflow-x-hidden">
      <section className="bp-section py-5 sm:py-8 lg:py-10">
        <div className="bp-ticket">
          <aside
            className="bp-stub-desktop relative z-10 shrink-0 flex-col items-center justify-between gap-6 overflow-hidden py-8"
            aria-hidden
          >
            <span className="rotate-180 text-[11px] font-bold tracking-[0.32em] text-brand-blue-900 [writing-mode:vertical-rl]">
              О!ХОЧУ
            </span>
            <div className="flex w-10 flex-col items-stretch gap-[3px]">
              {[3, 1, 2, 1, 1, 3, 2, 1, 4, 1, 2, 3, 1, 2, 1, 1, 3, 2, 1, 4, 2, 1, 3, 1].map((h, i) => (
                <span key={i} style={{ height: h }} className="w-full bg-brand-blue-900" />
              ))}
            </div>
            <span className="text-[10px] font-semibold tracking-[0.2em] text-brand-blue-900/65">№ 001</span>
          </aside>
          <div className="bp-stub-mobile relative z-10 items-center gap-3 overflow-hidden px-5 py-3" aria-hidden>
            <Ticket size={18} className="shrink-0 text-brand-blue-900" />
            <span className="text-xs font-bold tracking-[0.2em] text-brand-blue-900">О!ХОЧУ</span>
            <div className="ml-auto flex h-5 items-stretch gap-[2px]">
              {[3, 1, 2, 1, 2, 3, 1, 2, 1, 4, 2, 1, 3, 2].map((w, i) => (
                <span key={i} style={{ width: w }} className="bg-brand-blue-900" />
              ))}
            </div>
          </div>

          <div className="bp-body px-5 py-8 sm:px-9 sm:py-9 lg:px-12">
            <div className="relative z-10 mx-auto max-w-3xl text-center">
              <div className="bp-head !justify-center sm:!justify-between">
                <span className="flex items-center gap-2 text-[13px] font-bold tracking-[0.16em] text-brand-blue-900">
                  <Plane size={16} aria-hidden />
                  О!ХОЧУ
                </span>
                <span className="ml-auto hidden items-center gap-2 sm:flex">
                  <span className="bp-label">Посадочный</span>
                  <span className="rounded-full bg-brand-blue-900 px-2.5 py-1 text-[10px] font-bold tracking-[0.12em] text-white">
                    № 001
                  </span>
                </span>
              </div>

              <h1 className="mt-7 text-[28px] font-semibold leading-[1.12] tracking-[-0.02em] text-text-primary sm:text-[40px] lg:text-[44px]">
                <span className="block">Увидели отель?</span>
                <span className="mt-1 block text-brand-blue-900 sm:mt-1.5">
                  <RotatingCityWord />
                </span>
              </h1>
              <p className="mx-auto mt-3 max-w-xl text-[15px] leading-6 text-text-secondary sm:text-base">
                Загрузите фото или скриншот — найдём отель или похожие варианты дешевле.
              </p>

              <div className="bp-route-panel mx-auto mt-6 max-w-2xl px-5 py-4 text-left">
                <div className="bp-route items-center">
                  <div className="min-w-0">
                    <p className="bp-label">Загрузка</p>
                    <p className="bp-code text-[24px] leading-none sm:text-[30px]">ФОТО</p>
                    <p className="mt-1 text-[12px] text-text-secondary">ваш скриншот</p>
                  </div>
                  <div className="relative h-5 min-w-10 flex-1 sm:mx-3" aria-hidden>
                    <div className="absolute inset-x-0 top-1/2 border-t border-dashed border-brand-blue-900/30" />
                    <span className="bp-fly">
                      <Plane size={18} />
                    </span>
                  </div>
                  <div className="min-w-0 text-right">
                    <p className="bp-label">Куда</p>
                    <RouteDestination />
                    <p className="mt-1 text-[12px] text-text-secondary">отель мечты</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="relative z-10 mx-auto mt-7 max-w-xl">
              <div className="relative min-h-[240px] w-full sm:min-h-[260px]">
                <AnimatePresence mode="wait">
                  {showPhotos ? (
                    <motion.div
                      key="photos"
                      className="absolute inset-0 flex items-center justify-center gap-2.5 sm:gap-3"
                      initial={{ opacity: 1 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0, y: 12 }}
                      transition={{ duration: 0.25, ease: 'easeOut' }}
                    >
                      {cities.map((city, index) => (
                        <motion.figure
                          key={city.name}
                          className="w-[72px] shrink-0 overflow-hidden rounded-2xl border border-white bg-white shadow-sm sm:w-[100px]"
                          initial={reduce ? false : { opacity: 0, y: 18 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.32, delay: index * 0.05, ease: 'easeOut' }}
                        >
                          <SafeImage src={city.src} alt={city.name} className="aspect-[3/4]" eager />
                          <figcaption className="bg-white px-1 py-1.5 text-center text-[10px] font-semibold text-brand-blue-950 sm:text-[11px]">
                            {city.name}
                          </figcaption>
                        </motion.figure>
                      ))}
                    </motion.div>
                  ) : null}

                  {showCard ? (
                    <motion.div
                      key="upload"
                      className="sand-reveal absolute inset-x-0 top-0"
                      initial={reduce ? { opacity: 1 } : { opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: reduce ? 0.1 : 0.4, ease: [0.22, 1, 0.36, 1] }}
                    >
                      {!reduce ? <span className="sand-grain" aria-hidden /> : null}
                      <UploadDropzone
                        onError={pushToast}
                        onFileAccepted={(file) => {
                          setUploaded({
                            file,
                            previewUrl: URL.createObjectURL(file),
                            name: file.name,
                            size: file.size,
                          })
                          navigate('/search/preview')
                        }}
                      />
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </div>
            </div>
          </div>
        </div>

        <section id="how" className="mx-auto mt-14 scroll-mt-24 sm:mt-16">
          <HowItWorks reduce={!!reduce} />
        </section>
      </section>

      <footer className="border-t border-border py-6 text-center text-sm text-text-muted">
        О!Хочу · визуальный поиск отеля
      </footer>
    </main>
  )
}

type HowPhase = 'idle' | 'numbers' | 'cards'

function HowItWorks({ reduce }: { reduce: boolean }) {
  const rootRef = useRef<HTMLDivElement>(null)
  const inView = useInView(rootRef, { once: true, amount: 0.35 })
  const [howPhase, setHowPhase] = useState<HowPhase>(reduce ? 'cards' : 'idle')

  useEffect(() => {
    if (reduce) {
      setHowPhase('cards')
      return
    }
    if (!inView) return
    setHowPhase('numbers')
    const t = window.setTimeout(() => setHowPhase('cards'), 920)
    return () => window.clearTimeout(t)
  }, [inView, reduce])

  const showCards = howPhase === 'cards'

  return (
    <div ref={rootRef}>
      <motion.div
        className="mx-auto max-w-2xl text-center"
        initial={reduce ? false : { opacity: 0, y: 8 }}
        animate={inView || reduce ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
        transition={{ duration: 0.24 }}
      >
        <h2 className="text-2xl font-bold text-brand-blue-950 sm:text-[28px]">Как это работает</h2>
        <p className="mt-3 text-[15px] leading-6 text-text-secondary sm:text-base">
          От скриншота до бронирования — четыре коротких шага.
        </p>
      </motion.div>

      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4 lg:gap-5">
        {steps.map((item, index) => {
          const Icon = item.icon
          return (
            <div key={item.step} className="relative flex min-h-[220px] flex-col items-center">
              <motion.div
                className="z-10 flex h-14 w-14 items-center justify-center rounded-full bg-brand-blue-950 text-xl font-extrabold text-white shadow-sm"
                initial={reduce ? false : { opacity: 0, scale: 0.55, y: 18 }}
                animate={
                  howPhase === 'idle'
                    ? { opacity: 0, scale: 0.55, y: 18 }
                    : showCards
                      ? { opacity: 1, scale: 0.92, y: 0 }
                      : { opacity: 1, scale: 1, y: 0 }
                }
                transition={{
                  type: 'spring',
                  stiffness: 420,
                  damping: 22,
                  delay: reduce ? 0 : index * 0.12,
                }}
              >
                {item.step}
              </motion.div>

              <motion.article
                className="group relative -mt-7 flex w-full flex-1 cursor-default flex-col overflow-hidden rounded-[24px] border border-border bg-white px-5 pb-5 pt-10 transition-[border-color,box-shadow] duration-200 hover:border-brand-green-400 hover:shadow-[0_16px_36px_-18px_rgba(14,23,77,0.25)]"
                initial={reduce ? false : { opacity: 0, y: 28, scale: 0.92 }}
                animate={
                  showCards
                    ? {
                        opacity: 1,
                        y: 0,
                        scale: 1,
                        boxShadow: '0 14px 34px -20px rgba(14, 23, 77, 0.22)',
                      }
                    : { opacity: 0, y: 28, scale: 0.92 }
                }
                transition={{
                  type: 'spring',
                  stiffness: 320,
                  damping: 24,
                  delay: reduce ? 0 : 0.08 + index * 0.1,
                }}
                whileHover={
                  reduce
                    ? undefined
                    : {
                        y: -6,
                        scale: 1.015,
                        transition: { type: 'spring', stiffness: 420, damping: 26 },
                      }
                }
              >
                <div
                  className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-brand-green-100/80"
                  aria-hidden
                />
                <div className="relative mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-green-100 text-brand-blue-950">
                  <Icon size={20} strokeWidth={2.1} aria-hidden />
                </div>
                <h3 className="relative text-[19px] font-bold leading-snug text-brand-blue-950">{item.title}</h3>
                <p className="relative mt-2 text-[15px] leading-5 text-text-secondary">{item.text}</p>
              </motion.article>
            </div>
          )
        })}
      </div>
    </div>
  )
}
