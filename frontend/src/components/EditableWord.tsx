import { useRef, useState } from 'react'
import type { Word } from '../types'

interface Props {
  word: Word
  onChange: (text: string) => void
}

export function EditableWord({ word, onChange }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(word.word)
  const cancelled = useRef(false)

  if (editing) {
    const commit = () => {
      const text = draft.trim()
      if (!cancelled.current && text && text !== word.word) onChange(text)
      setEditing(false)
    }
    return (
      <input
        autoFocus
        value={draft}
        size={Math.max(draft.length, 2)}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
          if (e.key === 'Escape') {
            cancelled.current = true
            setEditing(false)
          }
        }}
        className="max-w-full rounded bg-neutral-950 px-1 text-sm text-emerald-300 outline-none ring-1 ring-emerald-500"
      />
    )
  }

  return (
    <button
      type="button"
      title={`${word.start.toFixed(2)}s → ${word.end.toFixed(2)}s · clique para editar`}
      onClick={() => {
        cancelled.current = false
        setDraft(word.word)
        setEditing(true)
      }}
      className="max-w-full rounded px-1 text-left text-sm break-all text-neutral-200 hover:bg-neutral-700"
    >
      {word.word}
    </button>
  )
}
