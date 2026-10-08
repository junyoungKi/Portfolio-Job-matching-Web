import { FileText, RefreshCw, Trash2, UploadCloud } from 'lucide-react'
import { useRef, useState } from 'react'
import type { DragEvent } from 'react'
import type { Translation } from '../lib/i18n'

interface Props {
  t: Translation
  file: File | null
  disabled?: boolean
  onFile: (file: File | null) => void
  onInvalid: () => void
}

function isPdf(file: File): boolean {
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} MB`
  return `${Math.max(1, Math.round(bytes / 1024)).toLocaleString()} KB`
}

export function FileDropzone({ t, file, disabled, onFile, onInvalid }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const accept = (candidate: File | undefined) => {
    if (!candidate) return
    if (!isPdf(candidate)) {
      onInvalid()
      return
    }
    onFile(candidate)
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(false)
    if (disabled) return
    accept(e.dataTransfer.files[0])
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`rounded-xl border-2 border-dashed transition-all duration-200 ${
        dragging
          ? 'scale-[1.01] border-brand bg-brand-soft'
          : file
            ? 'border-ok/50 bg-ok-soft'
            : 'border-line-strong bg-surface-2/60 hover:border-brand hover:bg-brand-soft/60'
      } ${disabled ? 'opacity-60' : ''}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="sr-only"
        tabIndex={-1}
        disabled={disabled}
        aria-label={t.resumeLabel}
        onChange={(e) => {
          accept(e.target.files?.[0])
          e.target.value = ''
        }}
      />

      {file ? (
        <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-surface text-ok shadow-sm">
              <FileText className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-fg">{file.name}</p>
              <p className="tabular text-xs text-muted">PDF · {formatSize(file.size)}</p>
            </div>
          </div>
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-xs font-semibold text-fg transition-colors hover:bg-surface-2 disabled:cursor-not-allowed"
            >
              <RefreshCw className="size-3.5" aria-hidden="true" />
              {t.changeFile}
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onFile(null)}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-xs font-semibold text-bad transition-colors hover:bg-bad-soft disabled:cursor-not-allowed"
            >
              <Trash2 className="size-3.5" aria-hidden="true" />
              {t.removeFile}
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="group flex w-full cursor-pointer flex-col items-center gap-2 px-4 py-8 text-center disabled:cursor-not-allowed"
        >
          <span className="grid size-12 place-items-center rounded-full bg-surface text-brand-text shadow-sm transition-transform duration-200 group-hover:-translate-y-0.5">
            <UploadCloud className="size-6" aria-hidden="true" />
          </span>
          <span className="text-sm font-semibold text-fg">{dragging ? t.dropActive : t.dropHint}</span>
          <span className="text-xs text-muted">{t.dropSub}</span>
          <span className="mt-1 inline-flex h-9 items-center rounded-lg bg-brand px-4 text-xs font-semibold text-brand-on transition-colors group-hover:bg-brand-hover">
            {t.chooseFile}
          </span>
        </button>
      )}
    </div>
  )
}
