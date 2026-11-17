export function SelectionActions({
  hasSelection,
  onRedraw,
  onClear,
  onChangePhoto,
}: {
  hasSelection: boolean
  onRedraw: () => void
  onClear: () => void
  onChangePhoto: () => void
}) {
  const link =
    'rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40'
  return (
    <div className="flex flex-wrap items-center gap-1 sm:gap-2">
      <button
        type="button"
        className={`${link} border border-border bg-white text-text-primary hover:bg-surface-soft`}
        onClick={onRedraw}
        disabled={!hasSelection}
      >
        Обвести заново
      </button>
      <button
        type="button"
        className={`${link} text-text-secondary hover:bg-surface-soft hover:text-text-primary`}
        onClick={onClear}
        disabled={!hasSelection}
      >
        Отменить выделение
      </button>
      <button
        type="button"
        className={`${link} ml-auto text-brand-blue-900 hover:bg-brand-green-100`}
        onClick={onChangePhoto}
      >
        Выбрать другое фото
      </button>
    </div>
  )
}
