type SafeImageProps = {
  src: string
  alt: string
  className?: string
  fallbackSrc?: string
  eager?: boolean
}

export function SafeImage({
  src,
  alt,
  className = '',
  fallbackSrc = '/fallback/hotel.jpg',
  eager = true,
}: SafeImageProps) {
  const resolved = src?.trim() || fallbackSrc

  return (
    <div className={`relative overflow-hidden bg-[#e8eaee] ${className}`}>
      <img
        src={resolved}
        alt={alt}
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
        className="absolute inset-0 h-full w-full object-cover"
        onError={(e) => {
          const img = e.currentTarget
          if (img.dataset.fallback === '1') return
          img.dataset.fallback = '1'
          img.src = fallbackSrc
        }}
      />
    </div>
  )
}
