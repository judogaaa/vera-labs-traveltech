import { forwardRef, type InputHTMLAttributes } from 'react'

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, id, className = '', ...props },
  ref,
) {
  const inputId = id ?? props.name ?? label
  return (
    <label className="flex w-full flex-col gap-1.5" htmlFor={inputId}>
      <span className="text-sm font-medium text-text-primary">{label}</span>
      <input
        ref={ref}
        id={inputId}
        className={`h-12 rounded-2xl border bg-white px-4 text-[15px] text-text-primary outline-none transition-colors duration-150 placeholder:text-text-muted ${
          error ? 'border-error' : 'border-border focus:border-brand-blue-700'
        } ${className}`}
        {...props}
      />
      {error ? (
        <span className="text-sm text-error" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  )
})
