/**
 * Timezone aliases to normalize non-standard timezone names
 */
export const TIMEZONE_ALIASES: Record<string, string> = {
    'Asia/Calcutta': 'Asia/Kolkata',
}

/**
 * Resolve and validate a timezone string, returning undefined if invalid
 */
export function resolveTimeZone(timezone?: string): string | undefined {
    if (!timezone) return undefined
    const normalized = TIMEZONE_ALIASES[timezone] ?? timezone
    try {
        new Intl.DateTimeFormat(undefined, { timeZone: normalized }).format(new Date())
        return normalized
    } catch {
        return undefined
    }
}

/**
 * Parse an ISO date string that may or may not have a timezone offset
 */
export function parseApiDate(iso: string): Date {
    const hasOffset = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso)
    const normalized = hasOffset ? iso : `${iso}Z`
    return new Date(normalized)
}

/**
 * Format a date as: "Wednesday, September 27, 2026"
 */
export function fmtDate(iso: string, timezone?: string): string {
    const date = parseApiDate(iso)
    const safeTimezone = resolveTimeZone(timezone)
    const options: Intl.DateTimeFormatOptions = {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    }
    if (safeTimezone) {
        options.timeZone = safeTimezone
    }
    try {
        return date.toLocaleDateString(undefined, options)
    } catch {
        return date.toLocaleDateString(undefined, {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
        })
    }
}

/**
 * Format a datetime as title: "Wednesday, September 27, 2026 3PM"
 */
export function fmtDateTimeTitle(iso: string, timezone?: string): string {
    const date = parseApiDate(iso)
    const safeTimezone = resolveTimeZone(timezone)
    const dateOptions: Intl.DateTimeFormatOptions = {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
    }
    const timeOptions: Intl.DateTimeFormatOptions = { hour: 'numeric', hour12: true }
    if (safeTimezone) {
        dateOptions.timeZone = safeTimezone
        timeOptions.timeZone = safeTimezone
    }

    let datePart = ''
    let timePart = ''
    try {
        datePart = date.toLocaleDateString(undefined, dateOptions)
        timePart = date.toLocaleTimeString(undefined, timeOptions).replace(/\s/g, '').toUpperCase()
    } catch {
        datePart = date.toLocaleDateString(undefined, {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
        })
        timePart = date.toLocaleTimeString(undefined, { hour: 'numeric', hour12: true }).replace(/\s/g, '').toUpperCase()
    }

    return `${datePart} ${timePart}`
}

/**
 * Get the browser's current timezone
 */
export function getCurrentTimeZone(): string | undefined {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined
}

/**
 * Convert a local datetime-local input (YYYY-MM-DDTHH:mm) to ISO string
 */
export function localDateTimeToISO(localDateTime: string): string {
    return new Date(localDateTime).toISOString()
}

/**
 * Convert an ISO date to local datetime-local input format (YYYY-MM-DDTHH:mm)
 */
export function isoToLocalDateTime(iso: string): string {
    const date = parseApiDate(iso)
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    return local.toISOString().slice(0, 16)
}
