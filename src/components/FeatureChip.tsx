export function FeatureChip({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-border-default bg-surface-muted px-3 py-1 text-xs font-medium text-text-secondary">
      {children}
    </span>
  )
}
