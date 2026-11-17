import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { Search, Sparkles } from 'lucide-react'
import { AppleSelect } from '../components/AppleSelect'
import { CatalogHotelCard } from '../components/CatalogHotelCard'
import { PageEnter } from '../components/PageEnter'
import { EmptyState } from '../components/EmptyState'
import { Button } from '../components/Button'
import type { CatalogHotel } from '../types/catalog'
import {
  catalogHotels as initialCatalogHotels,
  ensureCatalogReady,
  getCatalogCountries,
  getTopChains,
} from '../data/catalogHotels'

type SortKey = 'photos' | 'name' | 'price-asc' | 'price-desc' | 'rating'

const PAGE_SIZE = 48

const sortLabels: Record<SortKey, string> = {
  photos: 'Больше фото',
  name: 'По названию',
  'price-asc': 'Сначала дешевле',
  'price-desc': 'Сначала дороже',
  rating: 'По рейтингу',
}

const countryAliases: Record<string, string[]> = {
  ОАЭ: ['оаэ', 'дубай', 'абу-даби', 'uae', 'dubai'],
  Турция: ['турция', 'turkey', 'istanbul', 'стамбул', 'анталья'],
  Египет: ['египет', 'egypt', 'каир', 'хургада', 'шарм'],
}

export function CatalogScreen() {
  const reduce = useReducedMotion()
  const [hotels, setHotels] = useState<CatalogHotel[]>(() => [...initialCatalogHotels])
  const [catalogReady, setCatalogReady] = useState(false)
  const [countries, setCountries] = useState<string[]>(['all'])
  const [chains, setChains] = useState<string[]>(['all'])
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)
  const [country, setCountry] = useState<string>('all')
  const [chain, setChain] = useState<string>('all')
  const [sort, setSort] = useState<SortKey>('photos')
  const [visible, setVisible] = useState(PAGE_SIZE)

  useEffect(() => {
    let cancelled = false
    void ensureCatalogReady().then(() => {
      if (cancelled) return
      setHotels([...initialCatalogHotels])
      setCountries(['all', ...getCatalogCountries()])
      setChains(['all', ...getTopChains(20)])
      setCatalogReady(true)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const filtered = useMemo(() => {
    const q = deferredQuery.trim().toLowerCase()
    let list = hotels.filter((hotel) => {
      if (country !== 'all' && hotel.country !== country) return false
      if (chain !== 'all' && hotel.chain !== chain) return false
      if (!q) return true
      const hay = [hotel.name, hotel.chain ?? '', hotel.city ?? '', hotel.country ?? '', ...(hotel.amenities ?? [])]
        .join(' ')
        .toLowerCase()
      if (hay.includes(q)) return true
      const aliases = hotel.country ? countryAliases[hotel.country] : undefined
      return Boolean(aliases?.some((alias) => alias.includes(q) || q.includes(alias)))
    })

    list = [...list]
    if (sort === 'photos') list.sort((a, b) => b.image_count - a.image_count || a.name.localeCompare(b.name, 'ru'))
    if (sort === 'name') list.sort((a, b) => a.name.localeCompare(b.name, 'en'))
    if (sort === 'price-asc') {
      list.sort((a, b) => (a.pricePerNight ?? 1e12) - (b.pricePerNight ?? 1e12))
    }
    if (sort === 'price-desc') {
      list.sort((a, b) => (b.pricePerNight ?? -1) - (a.pricePerNight ?? -1))
    }
    if (sort === 'rating') {
      list.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
    }
    return list
  }, [chain, country, deferredQuery, hotels, sort])

  const shown = filtered.slice(0, visible)

  return (
    <main className="pb-16">
      <section className="relative overflow-hidden border-b border-border">
        <div className="catalog-hero-wash absolute inset-0" aria-hidden />
        <div className="page-container relative z-10 py-10 sm:py-14">
          <PageEnter>
            <p className="text-sm font-semibold tracking-wide text-brand-blue-800">Каталог О!Хочу</p>
            <h1 className="mt-2 max-w-2xl text-3xl font-extrabold tracking-tight text-brand-blue-950 sm:text-5xl">
              {catalogReady
                ? `${hotels.length.toLocaleString('ru-RU')} отелей из базы`
                : 'Собираем каталог…'}
            </h1>
            <p className="mt-3 max-w-xl text-[15px] leading-6 text-text-secondary sm:text-base">
              Подборка направлений Турции, Египта и ОАЭ плюс демо-отели — фильтруйте по стране, сети
              или ищите по названию.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                to="/"
                className="inline-flex h-11 items-center gap-2 rounded-full bg-brand-blue-950 px-5 text-sm font-semibold text-white no-underline transition-colors hover:bg-brand-blue-900"
              >
                <Sparkles size={16} aria-hidden />
                Найти по фото
              </Link>
              <a
                href="#catalog-grid"
                className="inline-flex h-11 items-center rounded-full border border-border bg-white px-5 text-sm font-semibold text-brand-blue-950 no-underline transition-colors hover:border-brand-green-400 hover:bg-brand-green-100"
              >
                К списку отелей
              </a>
            </div>
          </PageEnter>
        </div>
      </section>

      <section className="page-container pt-6 sm:pt-8">
        <PageEnter delay={0.04}>
          <div className="sticky top-[68px] z-30 -mx-1 space-y-4 rounded-[24px] border border-border bg-white/95 p-3 shadow-[0_1px_2px_rgba(21,23,28,0.04)] backdrop-blur-md sm:mx-0 sm:p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              <label className="relative min-w-0 flex-1">
                <span className="sr-only">Поиск по каталогу</span>
                <Search
                  size={18}
                  className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-text-muted"
                  aria-hidden
                />
                <input
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value)
                    setVisible(PAGE_SIZE)
                  }}
                  placeholder="Дубай, Египет, Hilton, название отеля…"
                  className="h-12 w-full rounded-2xl border border-border bg-surface-soft pl-11 pr-4 text-[15px] text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-brand-blue-700 focus:bg-white"
                />
              </label>

              <AppleSelect
                className="lg:min-w-[220px]"
                label="Сортировка"
                value={sort}
                options={(Object.keys(sortLabels) as SortKey[]).map((key) => ({
                  value: key,
                  label: sortLabels[key],
                }))}
                onChange={(next) => {
                  setSort(next)
                  setVisible(PAGE_SIZE)
                }}
              />
            </div>

            <div className="flex gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {countries.map((item) => {
                const active = country === item
                const label = item === 'all' ? 'Все страны' : item === 'ОАЭ' ? 'ОАЭ / Дубай' : item
                return (
                  <button
                    key={item}
                    type="button"
                    onClick={() => {
                      setCountry(item)
                      setVisible(PAGE_SIZE)
                    }}
                    className={`shrink-0 rounded-full px-3.5 py-2 text-sm font-semibold transition-colors ${
                      active
                        ? 'bg-brand-green-500 text-brand-blue-950'
                        : 'bg-surface-muted text-text-secondary hover:bg-brand-green-100 hover:text-brand-blue-950'
                    }`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>

            <div className="flex gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {chains.map((item) => {
                const active = chain === item
                const label = item === 'all' ? 'Все сети' : item
                return (
                  <button
                    key={item}
                    type="button"
                    onClick={() => {
                      setChain(item)
                      setVisible(PAGE_SIZE)
                    }}
                    className={`shrink-0 rounded-full px-3.5 py-2 text-sm font-semibold transition-colors ${
                      active
                        ? 'bg-brand-blue-950 text-white'
                        : 'bg-surface-muted text-text-secondary hover:bg-brand-green-100 hover:text-brand-blue-950'
                    }`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </div>
        </PageEnter>

        <div id="catalog-grid" className="mt-6 scroll-mt-36 sm:mt-8">
          <div className="mb-5">
            <h2 className="text-xl font-bold text-brand-blue-950 sm:text-2xl">Отели в каталоге</h2>
            <p className="mt-1 text-sm text-text-secondary">
              {catalogReady
                ? `Показано ${shown.length.toLocaleString('ru-RU')} из ${filtered.length.toLocaleString('ru-RU')}`
                : 'Загружаем подборку отелей…'}
            </p>
          </div>

          {!catalogReady ? (
            <div
              className="flex min-h-[240px] items-center justify-center text-sm text-text-muted"
              aria-busy="true"
            >
              Загрузка каталога…
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              title="Ничего не нашлось"
              description="Сбросьте фильтр или попробуйте другое название."
              actionLabel="Сбросить фильтры"
              onAction={() => {
                setQuery('')
                setCountry('all')
                setChain('all')
                setSort('photos')
                setVisible(PAGE_SIZE)
              }}
            />
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {shown.map((hotel, index) => (
                  <motion.div
                    key={`${hotel.source}-${hotel.id}`}
                    initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12 }}
                    animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
                    transition={{
                      duration: 0.22,
                      delay: reduce ? 0 : Math.min(index % PAGE_SIZE, 8) * 0.03,
                      ease: 'easeOut',
                    }}
                  >
                    <CatalogHotelCard hotel={hotel} index={index} />
                  </motion.div>
                ))}
              </div>

              {visible < filtered.length ? (
                <div className="mt-8 flex justify-center">
                  <Button
                    variant="secondary"
                    onClick={() => setVisible((v) => v + PAGE_SIZE)}
                  >
                    Показать ещё ({Math.min(PAGE_SIZE, filtered.length - visible)})
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </div>
      </section>
    </main>
  )
}
