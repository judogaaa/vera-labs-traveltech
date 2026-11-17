import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ImagePlus, Lasso, Sparkles } from 'lucide-react'
import { UploadDropzone } from '../components/UploadDropzone'
import { FreehandImageSelector } from '../components/FreehandImageSelector'
import { SelectionPreview } from '../components/SelectionPreview'
import { SelectionActions } from '../components/SelectionActions'
import { Button } from '../components/Button'
import { useFlow } from '../context/FlowContext'
import type { FreehandSelection } from '../types/visualSearch'
import { createMaskedCrop } from '../utils/createMaskedCrop'
import { createSelectionMask } from '../utils/createSelectionMask'
import { loadImageElement } from '../utils/loadImage'
import { createObjectUrl, revokeObjectUrl } from '../utils/objectUrl'

export function UploadPreviewScreen() {
  const navigate = useNavigate()
  const { uploaded, setUploaded, setVisualSearch, clearVisualSearch, pushToast } = useFlow()
  const [replacing, setReplacing] = useState(false)
  const [selection, setSelection] = useState<FreehandSelection | null>(null)
  const [cropPreviewUrl, setCropPreviewUrl] = useState<string | null>(null)
  const [helper, setHelper] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!uploaded && !replacing) navigate('/', { replace: true })
  }, [uploaded, replacing, navigate])

  useEffect(() => {
    setSelection(null)
    setHelper(null)
    setCropPreviewUrl((prev) => {
      revokeObjectUrl(prev)
      return null
    })
    clearVisualSearch()
  }, [uploaded?.previewUrl, clearVisualSearch])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      if (!uploaded || !selection) {
        setCropPreviewUrl((prev) => {
          revokeObjectUrl(prev)
          return null
        })
        return
      }
      try {
        const { maskedCropBlob } = await createMaskedCrop(uploaded.file, selection)
        if (cancelled) return
        const url = createObjectUrl(maskedCropBlob)
        setCropPreviewUrl((prev) => {
          revokeObjectUrl(prev)
          return url
        })
      } catch {
        if (!cancelled) pushToast('Не удалось создать выделенную область')
      }
    }
    const t = window.setTimeout(() => void run(), 200)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [selection, uploaded, pushToast])

  useEffect(() => () => revokeObjectUrl(cropPreviewUrl), [cropPreviewUrl])

  if (!uploaded && !replacing) return null

  const startSearch = async (mode: 'full-image' | 'freehand-region') => {
    if (!uploaded) return
    setBusy(true)
    try {
      if (mode === 'freehand-region') {
        if (!selection) return
        const img = await loadImageElement(uploaded.file)
        const { maskedCropBlob, boxedCropBlob } = await createMaskedCrop(uploaded.file, selection)
        const selectionMaskBlob = await createSelectionMask(
          img.naturalWidth,
          img.naturalHeight,
          selection.points,
        )
        const preview = createObjectUrl(maskedCropBlob)
        setVisualSearch({
          originalFile: uploaded.file,
          originalPreviewUrl: uploaded.previewUrl,
          mode: 'freehand-region',
          selection,
          selectionMaskBlob,
          maskedCropBlob,
          boxedCropBlob,
          cropPreviewUrl: preview,
        })
      } else {
        setVisualSearch({
          originalFile: uploaded.file,
          originalPreviewUrl: uploaded.previewUrl,
          mode: 'full-image',
        })
      }
      navigate('/search/analyzing')
    } catch {
      pushToast('Не удалось подготовить поиск')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="catalog-hero-wash min-h-[calc(100vh-4rem)]">
      <div className="page-container py-8 sm:py-10">
        {uploaded && !replacing ? (
          <div className="mx-auto max-w-[1120px]">
            <header className="max-w-2xl">
              <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-brand-blue-900/70">
                Шаг 2 · выделение
              </p>
              <h1 className="mt-2 text-[28px] font-semibold leading-[1.15] tracking-[-0.02em] text-text-primary sm:text-[36px]">
                Что именно вам понравилось?
              </h1>
              <p className="mt-2 text-[15px] leading-6 text-text-secondary sm:text-base">
                Обведите пальцем нужную деталь — бассейн, номер или вид. Или ищите отель целиком.
              </p>
            </header>

            <div className="mt-7 grid gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(280px,0.9fr)] lg:items-start lg:gap-7">
              <section className="overflow-hidden rounded-3xl border border-border bg-white shadow-[0_12px_32px_-18px_rgba(45,49,55,0.18)]">
                <div className="border-b border-border/80 bg-surface-soft px-4 py-3 sm:px-5">
                  <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
                    <Lasso size={16} className="text-brand-blue-900" aria-hidden />
                    Обведите область на фото
                  </div>
                </div>
                <div className="p-3 sm:p-4">
                  <FreehandImageSelector
                    imageUrl={uploaded.previewUrl}
                    selection={selection}
                    onSelectionChange={setSelection}
                    onHelper={setHelper}
                    disabled={busy}
                  />
                </div>
                {helper ? (
                  <p className="border-t border-border px-4 py-3 text-sm text-warning sm:px-5">{helper}</p>
                ) : null}
                <div className="border-t border-border px-4 py-3 sm:px-5">
                  <SelectionActions
                    hasSelection={Boolean(selection)}
                    onRedraw={() => {
                      setSelection(null)
                      setHelper(null)
                    }}
                    onClear={() => {
                      setSelection(null)
                      setHelper(null)
                    }}
                    onChangePhoto={() => setReplacing(true)}
                  />
                </div>
              </section>

              <aside className="space-y-4 lg:sticky lg:top-24">
                {selection && cropPreviewUrl ? (
                  <SelectionPreview src={cropPreviewUrl} />
                ) : (
                  <div className="rounded-3xl border border-border bg-white p-5 shadow-[0_10px_28px_-18px_rgba(45,49,55,0.16)]">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-green-100 text-brand-blue-900">
                      <Sparkles size={17} aria-hidden />
                    </div>
                    <p className="mt-3 text-[15px] font-semibold text-text-primary">Пока ничего не выделено</p>
                    <p className="mt-1.5 text-sm leading-5 text-text-secondary">
                      Обведите деталь на фото — или сразу ищите отель целиком по всему кадру.
                    </p>
                  </div>
                )}

                <div className="hidden rounded-3xl border border-border bg-white p-4 shadow-[0_10px_28px_-18px_rgba(45,49,55,0.16)] lg:block">
                  <p className="mb-3 text-sm font-medium text-text-primary">
                    {selection ? 'Готово к поиску по детали' : 'Что искать?'}
                  </p>
                  <div className="flex flex-col gap-2.5">
                    <Button
                      fullWidth
                      disabled={!selection || busy}
                      onClick={() => void startSearch('freehand-region')}
                    >
                      Найти похожее
                    </Button>
                    <Button
                      fullWidth
                      variant="secondary"
                      disabled={busy}
                      onClick={() => void startSearch('full-image')}
                    >
                      Искать весь отель
                    </Button>
                  </div>
                  <p className="mt-3 text-center text-xs leading-4 text-text-muted">
                    {selection
                      ? 'Поиск по выделенной детали'
                      : 'Без выделения ищем по всему фото'}
                  </p>
                </div>
              </aside>
            </div>

            <div className="sticky bottom-3 z-20 mt-6 rounded-2xl border border-border bg-white/95 p-3 shadow-[0_10px_30px_-12px_rgba(45,49,55,0.25)] backdrop-blur lg:hidden">
              {selection && cropPreviewUrl ? (
                <p className="mb-2 px-1 text-sm font-medium text-text-primary">Область выбрана — можно искать</p>
              ) : null}
              <div className="flex flex-col gap-2">
                <Button
                  fullWidth
                  disabled={!selection || busy}
                  onClick={() => void startSearch('freehand-region')}
                >
                  Найти похожее
                </Button>
                <Button
                  fullWidth
                  variant="secondary"
                  disabled={busy}
                  onClick={() => void startSearch('full-image')}
                >
                  Искать весь отель
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-2xl">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-green-100 text-brand-blue-900">
              <ImagePlus size={22} aria-hidden />
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-[-0.02em] text-text-primary">
              Выберите другое фото
            </h1>
            <p className="mt-2 text-text-secondary">Загрузите новый кадр, чтобы продолжить поиск.</p>
            <div className="mt-6">
              <UploadDropzone
                onError={pushToast}
                onFileAccepted={(file) => {
                  setUploaded({
                    file,
                    previewUrl: URL.createObjectURL(file),
                    name: file.name,
                    size: file.size,
                  })
                  setReplacing(false)
                }}
              />
            </div>
            {replacing && uploaded ? (
              <button
                type="button"
                className="mt-4 text-sm font-medium text-brand-blue-900"
                onClick={() => setReplacing(false)}
              >
                Отменить замену
              </button>
            ) : null}
          </div>
        )}
      </div>
    </main>
  )
}
