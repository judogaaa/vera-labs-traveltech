import { motion } from 'framer-motion'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

/** Mask PAN for display — never show full sensitive groups; last 4 when complete enough. */
export function maskCardNumber(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 16)
  if (!digits) return '•••• •••• •••• ••••'
  const groups: string[] = []
  for (let i = 0; i < 16; i += 4) {
    const chunk = digits.slice(i, i + 4)
    if (!chunk) {
      groups.push('••••')
      continue
    }
    if (i < 12) {
      groups.push(chunk.length === 4 ? '••••' : '•'.repeat(chunk.length).padEnd(4, '•'))
    } else {
      groups.push(chunk.padEnd(4, '•'))
    }
  }
  if (digits.length >= 12) {
    groups[3] = digits.slice(12).padEnd(4, '•')
  }
  return groups.join(' ')
}

/** Decorative masked CVC — never render the real digits. */
export function maskCvcDisplay(raw: string): string {
  const len = Math.min(Math.max(raw.replace(/\D/g, '').length, 0), 4)
  if (len === 0) return '•••'
  return '•'.repeat(Math.max(len, 3))
}

const cardFaceClass =
  'absolute inset-0 flex flex-col justify-between overflow-hidden rounded-[22px] p-5 text-white sm:p-6'

const cardGradient =
  'linear-gradient(145deg, #0c36b0 0%, #0e41d2 42%, #1c286e 78%, #0e174d 100%)'

export function BrandedPaymentCard({
  holderName,
  number,
  expiry,
  flipped = false,
  cvcLength = '',
}: {
  holderName: string
  number: string
  expiry: string
  /** Flip to back when CVC field is focused. */
  flipped?: boolean
  /** Raw CVC string used only to size decorative bullets — digits are never shown. */
  cvcLength?: string
}) {
  const profile = useMotionProfile()
  const displayName = holderName.trim() || 'ИМЯ ФАМИЛИЯ'
  const displayExpiry = expiry || 'ММ/ГГ'
  const maskedNumber = maskCardNumber(number)
  const maskedCvc = maskCvcDisplay(cvcLength)

  return (
    <div className="relative aspect-[1.586/1] w-full" style={{ perspective: 1400 }}>
      <motion.div
        className="relative h-full w-full"
        style={{ transformStyle: 'preserve-3d' }}
        animate={{ rotateY: flipped ? 180 : 0 }}
        transition={profile.reduce ? { duration: 0.01 } : springs.soft}
        aria-hidden={false}
      >
        {/* Front */}
        <div
          className={cardFaceClass}
          style={{
            background: cardGradient,
            backfaceVisibility: 'hidden',
            WebkitBackfaceVisibility: 'hidden',
            boxShadow: '0 18px 40px -18px rgba(14,23,77,0.55)',
          }}
        >
          <div
            className="pointer-events-none absolute -right-10 -top-16 h-44 w-44 rounded-full bg-brand-green-400/25 blur-2xl"
            aria-hidden
          />
          <div
            className="pointer-events-none absolute -bottom-12 -left-8 h-36 w-36 rounded-full bg-white/10 blur-2xl"
            aria-hidden
          />

          <div className="relative flex items-start justify-between gap-3">
            <p className="text-[20px] font-extrabold tracking-tight">
              О!<span className="font-extrabold">Хочу</span>
            </p>
            <p className="rounded-full bg-white/15 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white/90">
              Демо
            </p>
          </div>

          <div className="relative">
            <motion.p
              key={maskedNumber}
              className="font-mono text-[18px] tracking-[0.14em] sm:text-[20px]"
              initial={profile.reduce ? false : { opacity: 0.55, y: 2 }}
              animate={{ opacity: 1, y: 0 }}
              transition={springs.snappy}
            >
              {maskedNumber}
            </motion.p>
            <div className="mt-4 flex items-end justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-wider text-white/55">Держатель</p>
                <motion.p
                  key={displayName}
                  className="truncate text-sm font-semibold uppercase tracking-wide"
                  initial={profile.reduce ? false : { opacity: 0.7 }}
                  animate={{ opacity: 1 }}
                  transition={springs.snappy}
                >
                  {displayName}
                </motion.p>
              </div>
              <div className="text-right">
                <p className="text-[10px] uppercase tracking-wider text-white/55">Срок</p>
                <motion.p
                  key={displayExpiry}
                  className="text-sm font-semibold tracking-wide"
                  initial={profile.reduce ? false : { opacity: 0.7 }}
                  animate={{ opacity: 1 }}
                  transition={springs.snappy}
                >
                  {displayExpiry}
                </motion.p>
              </div>
            </div>
          </div>
        </div>

        {/* Back */}
        <div
          className={cardFaceClass}
          style={{
            background: cardGradient,
            backfaceVisibility: 'hidden',
            WebkitBackfaceVisibility: 'hidden',
            transform: 'rotateY(180deg)',
            boxShadow: '0 18px 40px -18px rgba(14,23,77,0.55)',
          }}
        >
          <div className="relative flex items-start justify-between gap-3">
            <p className="text-[16px] font-extrabold tracking-tight opacity-90">О!Хочу</p>
            <p className="rounded-full bg-white/15 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white/90">
              Демо
            </p>
          </div>

          <div
            className="-mx-5 mt-3 h-11 bg-brand-blue-950/80 sm:-mx-6"
            aria-hidden
          />

          <div className="relative mt-auto flex items-end justify-between gap-3 pt-4">
            <div className="min-w-0 flex-1">
              <div className="h-8 rounded-md bg-white/90 px-3 py-1.5">
                <div className="flex h-full items-center justify-end">
                  <motion.span
                    key={maskedCvc}
                    className="font-mono text-sm tracking-[0.35em] text-brand-blue-950"
                    initial={profile.reduce ? false : { opacity: 0.5 }}
                    animate={{ opacity: 1 }}
                    transition={springs.snappy}
                  >
                    {maskedCvc}
                  </motion.span>
                </div>
              </div>
              <p className="mt-1.5 text-[10px] uppercase tracking-wider text-white/55">CVC</p>
            </div>
            <p className="max-w-[40%] text-right text-[10px] leading-snug text-white/50">
              Демо-карта. Код не сохраняется.
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
