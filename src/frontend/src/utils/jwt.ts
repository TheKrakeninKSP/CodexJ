export function parseJwt(token: string): { username?: string; is_privileged?: boolean } {
    try {
        return JSON.parse(atob(token.split('.')[1]))
    } catch {
        return {}
    }
}
