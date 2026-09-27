export function getApiErrorMessage(
    err: unknown,
    fallback: string,
    fieldLabels?: Record<string, string>,
): string {
    const detail = (err as { response?: { data?: { detail?: unknown; message?: unknown } } })
        ?.response?.data?.detail
    const message = (err as { response?: { data?: { detail?: unknown; message?: unknown } } })
        ?.response?.data?.message

    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail)) {
        const text = detail
            .map((item) => {
                if (typeof item === 'string') return item
                if (item && typeof item === 'object' && 'msg' in item) {
                    const msg = (item as { msg?: unknown }).msg
                    const loc = (item as { loc?: unknown[] }).loc
                    const rawField = Array.isArray(loc) && loc.length > 1 ? String(loc[loc.length - 1]) : ''
                    const field = rawField && fieldLabels?.[rawField] ? fieldLabels[rawField] : rawField
                    if (typeof msg === 'string' && field) return `${field}: ${msg}`
                    return typeof msg === 'string' ? msg : ''
                }
                return ''
            })
            .filter(Boolean)
            .join(', ')
        if (text) return text
    }

    if (typeof message === 'string' && message.trim()) return message
    return fallback
}
