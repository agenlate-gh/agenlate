/**
 * Getting work out of Agenlate: onto the clipboard, or into a file.
 *
 * What a room produces is the user's, and the point of producing it is to use
 * it somewhere else — a document, a CMS, an email. These are the two ways out.
 */

import type { Message, RoomDetail } from './agenlate'

/**
 * Copies text. True if it reached the clipboard.
 *
 * The modern API needs a secure page and a permission some browsers withhold,
 * so there is a fallback through a hidden text area — clumsy, but it works in
 * the places the first one does not. The caller shows the outcome either way:
 * a Copy button that silently did nothing is worse than no button.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    try {
      const area = document.createElement('textarea')
      area.value = text
      area.setAttribute('readonly', '')
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(area)
      return ok
    } catch {
      return false
    }
  }
}

/** Saves text as a file through the browser's own download. */
export function downloadText(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // Released on the next tick: revoking in the same one can cancel the
  // download in some browsers before it has started.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

/**
 * A name a file system will accept, from a name a person typed.
 *
 * Keeps letters and digits from any alphabet — a room called "Página de
 * ventas" should not become "P-gina-de-ventas".
 */
export function fileSlug(name: string): string {
  const slug = name
    .trim()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
  return slug || 'agenlate'
}

/** The whole conversation as one Markdown document, in order. */
export function transcriptToMarkdown(room: RoomDetail, transcript: Message[]): string {
  const lines = [`# ${room.name}`, '', `**Objective:** ${room.objective}`, '']
  for (const message of transcript) {
    const who = message.emitter === 'user' ? 'You' : message.emitter_name
    const when = new Date(message.created_at).toLocaleString()
    lines.push('---', '', `### ${who} · ${when}`, '', message.content, '')
  }
  return lines.join('\n')
}
