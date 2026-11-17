import { Button } from './Button'

export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
}: {
  title: string
  description: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="rounded-[24px] border border-border-default bg-white px-6 py-10 text-center">
      <h2 className="text-xl font-bold text-brand-blue-950">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-text-secondary">{description}</p>
      {actionLabel && onAction ? (
        <div className="mt-5">
          <Button onClick={onAction}>{actionLabel}</Button>
        </div>
      ) : null}
    </div>
  )
}

export function ErrorState({
  title,
  description,
  onRetry,
}: {
  title: string
  description: string
  onRetry?: () => void
}) {
  return (
    <div className="rounded-[24px] border border-error/20 bg-error-bg px-6 py-8 text-center">
      <h2 className="text-xl font-bold text-error">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-text-secondary">{description}</p>
      {onRetry ? (
        <div className="mt-5">
          <Button onClick={onRetry}>Попробовать снова</Button>
        </div>
      ) : null}
    </div>
  )
}

export function LoadingSkeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-bg-subtle ${className}`} aria-hidden />
}
