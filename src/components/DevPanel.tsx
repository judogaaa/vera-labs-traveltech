import { useSearchParams, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useFlow } from '../context/FlowContext'
import type { MatchScenario } from '../types/vision'
import { getLastSearchDiagnostics } from '../services/visionService'

const options: { value: MatchScenario; label: string }[] = [
  { value: 'exact', label: 'Auto retrieval' },
  { value: 'region', label: 'Force region mode' },
  { value: 'multiple', label: 'Multiple matches' },
  { value: 'none', label: 'No match' },
]

export function DevPanel() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const show = params.get('dev') === '1'
  const { scenario, setScenario, setUploaded, pushToast } = useFlow()
  const [diag, setDiag] = useState(getLastSearchDiagnostics())

  useEffect(() => {
    if (!show) return
    const id = window.setInterval(() => setDiag(getLastSearchDiagnostics()), 800)
    return () => window.clearInterval(id)
  }, [show])

  if (!show) return null

  const loadDemo = async (path: string, name: string) => {
    try {
      const res = await fetch(path)
      const blob = await res.blob()
      const file = new File([blob], name, { type: blob.type || 'image/jpeg' })
      setUploaded({
        file,
        previewUrl: URL.createObjectURL(file),
        name: file.name,
        size: file.size,
      })
      navigate('/search/preview')
      pushToast(`Demo: ${name}`)
    } catch {
      pushToast('Не удалось загрузить demo-фото')
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 max-h-[70vh] w-[240px] overflow-auto rounded-2xl border border-border bg-white p-3 shadow-sm">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">Dev scenario</p>
      <div className="flex flex-col gap-1">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => setScenario(option.value)}
            className={`rounded-xl px-3 py-2 text-left text-xs font-medium ${
              scenario === option.value
                ? 'bg-brand-blue-900 text-white'
                : 'bg-surface-muted text-text-secondary hover:bg-page'
            }`}
          >
            {option.label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => void loadDemo('/demo/hotels/rixos/01.jpg', 'exact-rixos.jpg')}
          className="mt-1 rounded-xl border border-border px-3 py-2 text-left text-xs font-semibold text-brand-blue-900 hover:bg-surface-muted"
        >
          Load Rixos exact
        </button>
        <button
          type="button"
          onClick={() => void loadDemo('/demo/hotels/akka/01.jpg', 'exact-akka.jpg')}
          className="rounded-xl border border-border px-3 py-2 text-left text-xs font-semibold text-brand-blue-900 hover:bg-surface-muted"
        >
          Load Akka exact
        </button>
      </div>
      {diag ? (
        <div className="mt-3 space-y-1 border-t border-border pt-2 text-[10px] leading-4 text-text-secondary">
          <p>
            <span className="font-semibold text-text-primary">mode:</span> {diag.mode}
          </p>
          <p>
            <span className="font-semibold text-text-primary">query:</span> {diag.queryType}
          </p>
          <p>
            <span className="font-semibold text-text-primary">fingerprint:</span>{' '}
            {diag.fingerprintMatch ? 'yes' : 'no'} ({diag.bestHashDistance ?? '—'})
          </p>
          <p>
            <span className="font-semibold text-text-primary">provider:</span> {diag.provider}
          </p>
          <p className="font-semibold text-text-primary">top images</p>
          {diag.topImageMatches.slice(0, 3).map((m) => (
            <p key={`${m.hotelId}-${m.imageUrl}`}>
              {m.hotelId.split('-')[0]} · d={m.hashDistance} · {m.score}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}
