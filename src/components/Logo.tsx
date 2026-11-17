import { Link } from 'react-router-dom'

export function Logo({ className = '' }: { className?: string }) {
  return (
    <Link
      to="/"
      className={`inline-flex items-baseline gap-0.5 rounded-xl px-1.5 py-0.5 text-[24px] font-extrabold tracking-tight text-brand-blue-950 no-underline transition-colors duration-150 hover:bg-brand-green-100 sm:text-[26px] ${className}`}
      aria-label="О!Хочу — на главную"
    >
      <span>О!</span>
      <span>Хочу</span>
    </Link>
  )
}
