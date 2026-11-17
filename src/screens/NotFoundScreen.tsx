import { useNavigate } from 'react-router-dom'
import { EmptyState } from '../components/EmptyState'

export function NotFoundScreen() {
  const navigate = useNavigate()
  return (
    <main className="page-container py-16">
      <EmptyState
        title="Страница не найдена"
        description="Проверьте адрес или вернитесь на главную — и найдём отель по фото."
        actionLabel="На главную"
        onAction={() => navigate('/')}
      />
    </main>
  )
}
