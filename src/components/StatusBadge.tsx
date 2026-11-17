export function StatusBadge({
  tone = 'success',
  children,
}: {
  tone?: 'success' | 'warning' | 'neutral'
  children: string
}) {
  const styles = {
    success: 'bg-success-bg text-success',
    warning: 'bg-warning-bg text-warning',
    neutral: 'bg-bg-subtle text-text-secondary',
  }
  return (
    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${styles[tone]}`}>
      {children}
    </span>
  )
}
