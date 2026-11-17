import { lazy, Suspense } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { LayoutGroup } from 'framer-motion'
import { FlowProvider } from '../context/FlowContext'
import { Header } from '../components/Header'
import { AppRouter } from './router'

const DevPanel = lazy(() =>
  import('../components/DevPanel').then((m) => ({ default: m.DevPanel })),
)

export default function App() {
  return (
    <BrowserRouter>
      <FlowProvider>
        <LayoutGroup id="oh-want">
          <div className="min-h-screen bg-page text-text-primary">
            <Header />
            <AppRouter />
            <Suspense fallback={null}>
              <DevPanel />
            </Suspense>
          </div>
        </LayoutGroup>
      </FlowProvider>
    </BrowserRouter>
  )
}
