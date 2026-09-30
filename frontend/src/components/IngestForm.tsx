import { useState } from 'react'

const LANGUAGES = [
  ['', 'Idioma: auto'],
  ['pt', 'Português'],
  ['en', 'Inglês'],
  ['es', 'Espanhol'],
] as const

interface Props {
  disabled: boolean
  language: string
  onLanguageChange: (lang: string) => void
  onUrl: (url: string) => void
  onFile: (file: File) => void
}

export function IngestForm({ disabled, language, onLanguageChange, onUrl, onFile }: Props) {
  const [url, setUrl] = useState('')

  return (
    <div className="space-y-2">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (url.trim()) onUrl(url.trim())
        }}
      >
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Cole a URL do vídeo (YouTube, Instagram, TikTok…)"
          disabled={disabled}
          className="min-w-0 flex-1 rounded-md bg-neutral-800 px-3 py-2 text-sm outline-none ring-1 ring-neutral-700 placeholder:text-neutral-500 focus:ring-emerald-500 disabled:opacity-50"
        />
        <button
          disabled={disabled || !url.trim()}
          className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-neutral-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Baixar
        </button>
      </form>

      <div className="flex gap-2">
        <label
          className={`flex flex-1 cursor-pointer items-center justify-center rounded-md border border-dashed border-neutral-700 px-3 py-2 text-sm text-neutral-300 hover:border-emerald-500 hover:text-emerald-400 ${
            disabled ? 'pointer-events-none opacity-40' : ''
          }`}
        >
          ⬆ Upload de arquivo
          <input
            type="file"
            accept="video/*"
            className="hidden"
            disabled={disabled}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) onFile(file)
              e.target.value = ''
            }}
          />
        </label>
        <select
          value={language}
          onChange={(e) => onLanguageChange(e.target.value)}
          disabled={disabled}
          className="rounded-md bg-neutral-800 px-2 text-sm ring-1 ring-neutral-700 outline-none disabled:opacity-50"
        >
          {LANGUAGES.map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
