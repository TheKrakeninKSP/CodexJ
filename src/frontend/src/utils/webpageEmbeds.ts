import type { MediaRecord } from '../services/api'

export type WebpageEmbedValue = {
  src: string
  source_url: string
  title: string
  media_id?: string
  status?: MediaRecord['status']
  error_message?: string | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function getWebpageMetadata(media: MediaRecord): Record<string, unknown> {
  if (!isRecord(media.custom_metadata)) return {}
  return media.custom_metadata
}

export function getWebpageSourceLabel(sourceUrl: string): string {
  return sourceUrl.trim() || 'Original URL unavailable'
}

export function mediaToWebpageEmbed(
  media: MediaRecord,
  fallback?: Partial<WebpageEmbedValue>,
): WebpageEmbedValue {
  const metadata = getWebpageMetadata(media)
  const sourceUrl = typeof metadata.source_url === 'string'
    ? metadata.source_url
    : fallback?.source_url ?? media.resource_path
  const title = typeof metadata.page_title === 'string'
    ? metadata.page_title
    : fallback?.title ?? ''

  return {
    src: media.resource_path,
    source_url: sourceUrl,
    title,
    media_id: media.id,
    status: media.status,
    error_message: media.error_message ?? null,
  }
}

function nodeToEmbed(el: Element): WebpageEmbedValue | null {
  const src = el.getAttribute('data-src') ?? ''
  const sourceUrl = el.getAttribute('data-source-url') ?? src
  const title = el.getAttribute('data-title') ?? ''
  const mediaIdAttr = el.getAttribute('data-media-id')
  const mediaId = mediaIdAttr || undefined
  const rawStatus = el.getAttribute('data-status')
  const status: MediaRecord['status'] =
    rawStatus === 'pending' || rawStatus === 'failed' ? rawStatus : 'completed'
  const errorMessage = el.getAttribute('data-error-message') || null

  if (!src && !sourceUrl) return null
  return { src, source_url: sourceUrl, title, media_id: mediaId, status, error_message: errorMessage }
}

// Accepts both HTML string (new format) and legacy Delta object (old format).
// Returns [] for legacy bodies — the reader will show no webpage section cards.
export function extractWebpageEmbeds(body: unknown): WebpageEmbedValue[] {
  if (typeof body !== 'string') return []

  const doc = new DOMParser().parseFromString(body, 'text/html')
  const nodes = doc.querySelectorAll('div[data-type="webpage"]')
  const embeds: WebpageEmbedValue[] = []
  const seen = new Set<string>()

  for (const el of nodes) {
    const embed = nodeToEmbed(el)
    if (!embed) continue
    const key = embed.src || embed.source_url
    if (!key || seen.has(key)) continue
    seen.add(key)
    embeds.push(embed)
  }
  return embeds
}

export function listPendingWebpageMediaIds(body: unknown): string[] {
  return extractWebpageEmbeds(body)
    .filter((e) => e.status === 'pending' && typeof e.media_id === 'string')
    .map((e) => e.media_id as string)
}

// Updates webpage embed attributes in an HTML string for nodes whose media_id matches.
// Returns the original string unchanged if nothing changed.
export function syncWebpageEmbedsWithMedia(
  body: unknown,
  mediaById: Map<string, MediaRecord>,
): unknown {
  if (typeof body !== 'string') return body

  const doc = new DOMParser().parseFromString(body, 'text/html')
  let changed = false

  for (const el of doc.querySelectorAll('div[data-type="webpage"]')) {
    const mediaId = el.getAttribute('data-media-id')
    if (!mediaId) continue
    const media = mediaById.get(mediaId)
    if (!media) continue
    const current = nodeToEmbed(el)
    if (!current) continue
    const next = mediaToWebpageEmbed(media, current)
    if (
      next.src !== current.src
      || next.source_url !== current.source_url
      || next.title !== current.title
      || next.status !== current.status
      || next.error_message !== current.error_message
    ) {
      el.setAttribute('data-src', next.src)
      el.setAttribute('data-source-url', next.source_url)
      el.setAttribute('data-title', next.title)
      el.setAttribute('data-status', next.status ?? 'completed')
      el.setAttribute('data-error-message', next.error_message ?? '')
      changed = true
    }
  }

  if (!changed) return body
  return doc.body.innerHTML
}
