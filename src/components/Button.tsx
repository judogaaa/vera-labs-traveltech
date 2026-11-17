import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'soft'
type Size = 'sm' | 'md' | 'lg'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
  fullWidth?: boolean
  children: ReactNode
}

const variants: Record<Variant, string> = {
  primary:
    'bg-brand-blue-900 text-white hover:bg-brand-blue-800 hover:ring-2 hover:ring-brand-green-400/70 hover:ring-offset-1 active:bg-brand-blue-950 disabled:bg-border-strong disabled:text-text-muted disabled:active:scale-100 disabled:hover:ring-0',
  secondary:
    'bg-white text-brand-blue-900 border border-border-strong hover:border-brand-green-400 hover:bg-brand-green-100 active:bg-brand-green-200 disabled:text-text-muted disabled:active:scale-100',
  ghost:
    'bg-transparent text-brand-blue-900 hover:bg-brand-green-100 active:bg-brand-green-200 disabled:text-text-muted disabled:active:scale-100',
  soft: 'bg-brand-green-100 text-brand-blue-950 hover:bg-brand-green-200 active:bg-brand-green-200 disabled:bg-surface-muted disabled:text-text-muted disabled:active:scale-100',
}

const sizes: Record<Size, string> = {
  sm: 'h-10 min-h-10 px-3.5 text-sm rounded-xl',
  md: 'h-11 min-h-11 px-4 text-[15px] rounded-2xl',
  lg: 'h-12 min-h-12 px-5 text-base rounded-2xl',
}

export function Button({
  variant = 'primary',
  size = 'md',
  fullWidth,
  className = '',
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 font-semibold transition-[color,background-color,border-color,transform] duration-150 ease-out active:scale-[0.98] disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]} ${fullWidth ? 'w-full' : ''} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
