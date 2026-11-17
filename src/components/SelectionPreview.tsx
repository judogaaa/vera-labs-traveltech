export function SelectionPreview({ src }: { src: string }) {
  return (
    <div className="overflow-hidden rounded-3xl border border-border bg-white shadow-[0_10px_28px_-18px_rgba(45,49,55,0.16)]">
      <div className="border-b border-border/80 bg-surface-soft px-4 py-3">
        <p className="text-sm font-semibold text-text-primary">Будем искать по этой детали</p>
      </div>
      <div className="p-4">
        <div className="overflow-hidden rounded-2xl border border-border bg-[linear-gradient(45deg,#eef0f2_25%,transparent_25%,transparent_75%,#eef0f2_75%),linear-gradient(45deg,#eef0f2_25%,transparent_25%,transparent_75%,#eef0f2_75%)] bg-[length:14px_14px] bg-[position:0_0,7px_7px] bg-white">
          <img src={src} alt="Выделенная деталь" className="mx-auto max-h-44 w-auto object-contain" />
        </div>
        <p className="mt-3 text-sm leading-5 text-text-secondary">
          Маска готова — можно искать похожие отели.
        </p>
      </div>
    </div>
  )
}
