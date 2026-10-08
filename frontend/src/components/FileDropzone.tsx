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
    <div>
      <span className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">{t.resumeLabel}</span>
      <div
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`rounded-2xl border-2 border-dashed p-6 text-center transition-colors ${
          dragging
            ? 'border-blue-400 bg-blue-500/10'
            : file
              ? 'border-emerald-500/40 bg-emerald-500/5'
              : 'border-slate-700 bg-slate-900/50 hover:border-slate-500'
        } ${disabled ? 'opacity-60' : ''}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          className="sr-only"
          disabled={disabled}
          aria-label={t.resumeLabel}
          onChange={(e) => {
            accept(e.target.files?.[0])
            e.target.value = ''
          }}
        />

        {file ? (
          <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-emerald-500/15 text-emerald-400">
                <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
                  <path d="M14 3v5h5" />
                </svg>
              </div>
              <div className="min-w-0 text-left">
                <p className="truncate text-sm font-semibold text-white">{file.name}</p>
                <p className="text-xs text-slate-500">{(file.size / 1024).toLocaleString(undefined, { maximumFractionDigits: 0 })} KB</p>
              </div>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                disabled={disabled}
                onClick={() => inputRef.current?.click()}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed"
              >
                {t.changeFile}
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onFile(null)}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-500/10 disabled:cursor-not-allowed"
              >
                {t.removeFile}
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            disabled={disabled}
            onClick={() => inputRef.current?.click()}
            className="flex w-full cursor-pointer flex-col items-center gap-2 disabled:cursor-not-allowed"
          >
            <svg viewBox="0 0 24 24" className="size-8 text-slate-500" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 16V4m0 0l-4 4m4-4l4 4" />
              <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
            </svg>
            <span className="text-sm font-medium text-slate-300">{dragging ? t.dropActive : t.dropHint}</span>
            <span className="rounded-full bg-blue-600 px-4 py-1.5 text-xs font-bold text-white">{t.chooseFile}</span>
          </button>
        )}
      </div>
    </div>
  )
}
