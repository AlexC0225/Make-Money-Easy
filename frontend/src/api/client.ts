const API_PREFIX = '/api/v1'

type RequestOptions = RequestInit & {
  params?: Record<string, string | number | boolean | undefined>
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers, ...rest } = options
  const search = new URLSearchParams()

  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        search.set(key, String(value))
      }
    })
  }

  const response = await fetch(`${API_PREFIX}${path}${search.size ? `?${search}` : ''}`, {
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    ...rest,
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new ApiError(payload?.detail ?? 'Request failed', response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export { request }
