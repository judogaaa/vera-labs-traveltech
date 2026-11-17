import type { ButtonHTMLAttributes, ReactNode } from 'react'

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string
  children: ReactNode
}

export function IconButton({ label, children, className = '', ...props }: IconButtonProps) {
  return (
    <button
      aria-label={label}
      className={`inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-border-default bg-white text-brand-blue-900 transition-colors hover:border-brand-green-400 hover:bg-brand-green-100 disabled:opacity-50 ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
