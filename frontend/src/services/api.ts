import axios from 'axios'
import { useAuthStore } from '../stores/authStore'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
})

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(err)
  },
)

export default api

// ── Typed helpers ─────────────────────────────────────────────────────────────

export const authApi = {
  register: (username: string, password: string) =>
    api.post<{ access_token: string; token_type: string; hashkey: string }>(
      '/auth/register',
      { username, password },
    ),
  login: (username: string, password: string) =>
    api.post<{ access_token: string; token_type: string }>('/auth/login', {
      username,
      password,
    }),
  unlock: (username: string, hashkey: string) =>
    api.post<{ access_token: string; token_type: string }>('/auth/unlock', {
      username,
      hashkey,
    }),
  delete: () => api.delete<{ status: string; message: string }>('/auth/delete'),
  registerWithImport: (encryption_key: string, file: File) => {
    const form = new FormData()
    form.append('encryption_key', encryption_key)
    form.append('file', file)
    return api.post<RegisterWithImportResponse>('/auth/register-with-import', form)
  },
}

export const workspacesApi = {
  list: () => api.get<Workspace[]>('/workspaces'),
  create: (name: string) => api.post<Workspace>('/workspaces', { name }),
  update: (id: string, name: string) =>
    api.patch<Workspace>(`/workspaces/${id}`, { name }),
  remove: (id: string) => api.delete(`/workspaces/${id}`),
}

export const journalsApi = {
  list: (workspaceId: string) =>
    api.get<Journal[]>(`/workspaces/${workspaceId}/journals`),
  create: (workspaceId: string, name: string, description?: string) =>
    api.post<Journal>(`/workspaces/${workspaceId}/journals`, {
      name,
      description,
    }),
  update: (
    workspaceId: string,
    journalId: string,
    data: Partial<{ name: string; description: string }>,
  ) => api.patch<Journal>(`/workspaces/${workspaceId}/journals/${journalId}`, data),
  remove: (workspaceId: string, journalId: string) =>
    api.delete(`/workspaces/${workspaceId}/journals/${journalId}`),
}

export const entriesApi = {
  list: (journalId: string) =>
    api.get<Entry[]>(`/journals/${journalId}/entries`),
  create: (journalId: string, data: EntryCreate) =>
    api.post<Entry>(`/journals/${journalId}/entries`, data),
  get: (id: string) => api.get<Entry>(`/entries/${id}`),
  update: (id: string, data: Partial<EntryCreate>) =>
    api.patch<Entry>(`/entries/${id}`, data),
  remove: (id: string) => api.delete(`/entries/${id}`),
  search: (params: {
    q: string
    journal_id?: string
    entry_type?: string
    from?: string
    to?: string
  }) => api.get<Entry[]>('/entries/search', { params }),
}

export const entryTypesApi = {
  list: () => api.get<EntryType[]>('/entry-types'),
  create: (name: string) => api.post<EntryType>('/entry-types', { name }),
  remove: (id: string) => api.delete(`/entry-types/${id}`),
}

export const mediaApi = {
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<{
      resource_path: string
      media_type: string
      original_filename: string
      file_size: number
      created_at: string
      custom_metadata: Record<string, unknown> | null
    }>(
      '/media/upload',
      form,
    )
  },
  trim: () =>
    api.post<{ status: string; deleted_count: number; scanned_count: number }>(
      '/media/trim',
    ),
}

export const dataManagementApi = {
  export: (encryption_key: string) =>
    api.post<ExportResponse>('/data-management/export', { encryption_key }),
  download: (filename: string) =>
    api.get(`/data-management/export/download/${filename}`, {
      responseType: 'blob',
    }),
  importEncrypted: (
    file: File,
    encryption_key: string,
    conflict_resolution = 'skip',
  ) => {
    const form = new FormData()
    form.append('file', file)
    form.append('encryption_key', encryption_key)
    form.append('conflict_resolution', conflict_resolution)
    return api.post<ImportResponse>('/data-management/import/encrypted', form)
  },
}

// ── Shared types ──────────────────────────────────────────────────────────────

export interface Workspace {
  id: string
  name: string
  created_at: string
}

export interface Journal {
  id: string
  workspace_id: string
  name: string
  description?: string
  created_at: string
}

export interface MetadataField {
  key: string
  value: string
}

export interface Entry {
  id: string
  journal_id: string
  type: string
  name: string
  timezone?: string
  body: object
  custom_metadata: MetadataField[]
  media_refs: string[]
  date_created: string
  updated_at: string
}

export interface EntryCreate {
  type: string
  name?: string
  timezone?: string
  body: object
  custom_metadata: MetadataField[]
  date_created?: string
}

export interface EntryType {
  id: string
  name: string
}

export interface ExportResponse {
  status: string
  filename: string
  message?: string
  timestamp: string
}

export interface ImportResponse {
  status: string
  message: string
  workspaces_imported: number
  journals_imported: number
  entries_imported: number
  entry_types_imported: number
  skipped: number
  errors: string[]
}

export interface RegisterWithImportResponse {
  username: string
  access_token: string
  token_type: string
  import_result: { status: string }
}
