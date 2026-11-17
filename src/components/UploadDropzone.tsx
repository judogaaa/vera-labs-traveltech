import { useCallback, useRef, useState, type DragEvent, type KeyboardEvent } from 'react'
import { ImagePlus } from 'lucide-react'
import { motion, useReducedMotion } from 'framer-motion'
import { Button } from './Button'
import { ACCEPTED_TYPES, validateImageFile } from '../lib/format'

type UploadDropzoneProps = {
  onFileAccepted: (file: File) => void
  onError: (message: string) => void
}

export function UploadDropzone({ onFileAccepted, onError }: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const reduce = useReducedMotion()

  const handleFile = useCallback(
    (file: File | undefined) => {
      if (!file) return
      const error = validateImageFile(file)
      if (error) {
        onError(error)
        return
      }
      onFileAccepted(file)
    },
    [onError, onFileAccepted],
  )

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files?.[0])
  }

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      inputRef.current?.click()
    }
  }

  return (
    <motion.div
      role="button"
      tabIndex={0}
      aria-label="Загрузить фото отеля"
      onKeyDown={onKeyDown}
      onDragEnter={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={(e) => {
        e.preventDefault()
        setDragging(false)
      }}
      onDrop={onDrop}
      animate={
        reduce
          ? undefined
          : dragging
            ? { scale: 1.01 }
            : { scale: 1 }
      }
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className={`rounded-xl border border-dashed p-7 text-center transition-[border-color,background-color,box-shadow] duration-200 sm:p-9 ${
        dragging
          ? 'border-brand-blue-800 bg-brand-green-100 shadow-sm'
          : 'border-brand-blue-900/25 bg-white/80 hover:border-brand-blue-900/45 hover:bg-brand-green-100/60'
      }`}
    >
      <motion.div
        className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-bg-subtle text-brand-blue-900"
        animate={reduce ? undefined : dragging ? { y: -2 } : { y: 0 }}
        transition={{ duration: 0.18 }}
      >
        <ImagePlus size={28} aria-hidden />
      </motion.div>
      <p className="text-lg font-semibold text-brand-blue-950">Перетащите фото сюда</p>
      <p className="mt-1 text-sm text-text-secondary">или выберите файл</p>
      <div className="mt-5">
        <Button type="button" onClick={() => inputRef.current?.click()}>
          Загрузить фото
        </Button>
      </div>
      <p className="mt-4 text-xs text-text-tertiary">JPG, PNG, WEBP до 10 МБ</p>
      <input
        ref={inputRef}
        type="file"
        accept={[...ACCEPTED_TYPES, '.jpg', '.jpeg', '.png', '.webp'].join(',')}
        className="sr-only"
        onChange={(e) => {
          handleFile(e.target.files?.[0])
          e.target.value = ''
        }}
      />
    </motion.div>
  )
}
