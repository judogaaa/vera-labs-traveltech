import type { InputHTMLAttributes } from 'react'

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  label: string
}

export function Checkbox({ label, id, className = '', ...props }: CheckboxProps) {
  const inputId = id ?? props.name ?? 'checkbox'
  return (
    <label htmlFor={inputId} className={`flex cursor-pointer items-start gap-3 ${className}`}>
      <input
        id={inputId}
        type="checkbox"
        className="mt-1 h-5 w-5 rounded border-border-strong accent-brand-blue-900"
        {...props}
      />
      <span className="text-sm leading-5 text-text-secondary">{label}</span>
    </label>
  )
}
