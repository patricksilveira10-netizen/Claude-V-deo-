import { useEffect, useState } from 'react'
import { getHealth } from '../lib/api'
import type { Health } from '../types'

const POLL_MS = 3000

type Tone = 'ok' | 'warn' | 'bad' | 'idle'

function describe(health: Health | 'offline'): { tone: Tone; text: string; title?: string } {
  if (health === 'offline') return { tone: 'bad', text: 'API offline — rode ./start.sh (ou start.bat)' }
  if (!health.ffmpeg) return { tone: 'bad', text: 'FFmpeg/ffprobe não encontrado no PATH' }
  const { state, model, error, load_seconds } = health.whisper
  switch (state) {
    case 'ready':
      return { tone: 'ok', text: `Whisper “${model}” pronto`, title: `carregado em ${load_seconds}s` }
    case 'loading':
      return { tone: 'warn', text: `Whisper “${model}”: carregando (1ª vez baixa o modelo)…` }
    case 'error':
      return { tone: 'bad', text: `Whisper “${model}”: erro ao carregar`, title: error ?? undefined }
    default:
      return { tone: 'idle', text: `Whisper “${model}”: carrega na 1ª análise` }
  }
}

/** Estado da API e do Whisper. Consulta até o modelo ficar pronto (na 1ª execução ele é baixado). */
export function ApiStatus() {
  const [health, setHealth] = useState<Health | 'offline' | null>(null)

  useEffect(() => {
    let timer: number | undefined
    let cancelled = false
    const poll = async () => {
      let next: Health | 'offline'
      try {
        next = await getHealth()
      } catch {
        next = 'offline'
      }
      if (cancelled) return
      setHealth(next)
      if (next === 'offline' || next.whisper.state !== 'ready') timer = window.setTimeout(poll, POLL_MS)
    }
    poll()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [])

  if (health === null) return null
  const { tone, text, title } = describe(health)

  const colors = {
    ok: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/30',
    warn: 'bg-amber-500/10 text-amber-300 ring-amber-500/30',
    bad: 'bg-red-500/10 text-red-400 ring-red-500/30',
    idle: 'bg-neutral-800 text-neutral-400 ring-neutral-700',
  }[tone]
  const dot = { ok: 'bg-emerald-400', warn: 'bg-amber-300', bad: 'bg-red-400', idle: 'bg-neutral-500' }[tone]

  return (
    <span title={title} className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs ring-1 ${colors}`}>
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {text}
    </span>
  )
}
