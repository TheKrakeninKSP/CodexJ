import type { Entry, MediaRecord } from '../services/api'

export type WebpageEmbedValue = {
  src: string
  source_url: string
  title: string
  status?: MediaRecord['status']
  error_message?: string | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function normalizeWebpageEmbedValue(value: unknown): WebpageEmbedValue | null {
  if (typeof value === 'string' && value.trim()) {
    return {
      src: value,
      source_url: value,
      title: '',
      status: 'completed',
      error_message: null,
    }
  }

  if (!isRecord(value)) return null

  const src = typeof value.src === 'string' ? value.src : ''
  const sourceUrl = typeof value.source_url === 'string' ? value.source_url : src
  const title = typeof value.title === 'string' ? value.title : ''
  const status = value.status === 'pending' || value.status === 'failed'
    ? value.status
    : 'completed'
  const errorMessage = typeof value.error_message === 'string' ? value.error_message : null

  if (!src && !sourceUrl) return null

  return {
    src,
    source_url: sourceUrl,
    title,
    status,
    error_message: errorMessage,
  }
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
    status: media.status,
    error_message: media.error_message ?? null,
  }
}

export function extractWebpageEmbeds(body: Entry['body']): WebpageEmbedValue[] {
  if (!isRecord(body) || !Array.isArray(body.ops)) return []

  const embeds: WebpageEmbedValue[] = []
  const seen = new Set<string>()

  for (const op of body.ops) {
    if (!isRecord(op) || !isRecord(op.insert) || !('webpage' in op.insert)) continue
    const embed = normalizeWebpageEmbedValue(op.insert.webpage)
    if (!embed) continue

    const key = embed.src || embed.source_url
    if (!key || seen.has(key)) continue
    seen.add(key)
    embeds.push(embed)
  }

  return embeds
}

export function listPendingWebpageResourcePaths(body: Entry['body']): string[] {
  return extractWebpageEmbeds(body)
    .filter((embed) => embed.status === 'pending' && embed.src)
    .map((embed) => embed.src)
}

export function syncWebpageEmbedsWithMedia(
  body: Entry['body'],
  mediaByPath: Map<string, MediaRecord>,
): Entry['body'] {
  if (!isRecord(body) || !Array.isArray(body.ops)) return body

  let changed = false
  const nextOps = body.ops.map((op) => {
    if (!isRecord(op) || !isRecord(op.insert) || !('webpage' in op.insert)) return op

    const currentEmbed = normalizeWebpageEmbedValue(op.insert.webpage)
    if (!currentEmbed?.src) return op

    const media = mediaByPath.get(currentEmbed.src)
    if (!media) return op

    const nextEmbed = mediaToWebpageEmbed(media, currentEmbed)
    const hasChanged =
      nextEmbed.src !== currentEmbed.src
      || nextEmbed.source_url !== currentEmbed.source_url
      || nextEmbed.title !== currentEmbed.title
      || nextEmbed.status !== currentEmbed.status
      || nextEmbed.error_message !== currentEmbed.error_message

    if (!hasChanged) return op

    changed = true
    return {
      ...op,
      insert: {
        ...op.insert,
        webpage: nextEmbed,
      },
    }
  })

  if (!changed) return body

  return {
    ...body,
    ops: nextOps,
  }
}