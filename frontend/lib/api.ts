/**
 * The client for our backend.
 *
 * Every request carries the caller's Supabase token, because the backend uses
 * it to talk to the database *as that user* — which is what makes row-level
 * security apply. A request without it is not merely unauthenticated; it has
 * no identity for the database to filter on.
 *
 * Errors arrive in one shape from the API and leave here in one shape too, so
 * a screen can show `error.message` without knowing which endpoint failed.
 */

import { env } from './env'
import { getAccessToken } from './supabase'

export type ApiErrorCode =
  | 'unauthenticated'
  | 'not_found'
  | 'bad_request'
  | 'conflict'
  | 'invalid_request'
  | 'key_rejected'
  | 'out_of_credit'
  | 'rate_limited'
  | 'provider_unavailable'
  | 'unavailable'
  | 'provider_error'
  | 'internal_error'
  | 'network'

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number
  /** Quote this when reporting a problem; it finds the whole request in the logs. */
  readonly requestId: string | null

  constructor(
    message: string,
    code: ApiErrorCode,
    status: number,
    requestId: string | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.requestId = requestId
  }

  /** Whether signing in again is what fixes this. */
  get needsSignIn(): boolean {
    return this.code === 'unauthenticated'
  }

  /** Whether this is about the user's OpenRouter key rather than our system. */
  get isKeyProblem(): boolean {
    return this.code === 'key_rejected' || this.code === 'out_of_credit'
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken()
  if (!token) {
    throw new ApiError('You are not signed in.', 'unauthenticated', 401)
  }
  return { Authorization: `Bearer ${token}` }
}

async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get('X-Request-ID')
  let message = 'Something went wrong.'
  let code: ApiErrorCode = 'internal_error'

  try {
    const body = await response.json()
    if (body?.error) {
      message = body.error.message ?? message
      code = body.error.code ?? code
    }
  } catch {
    // A response that is not our error envelope — a proxy timeout page, say.
    // The status is still worth reporting.
    message = `The server returned ${response.status}.`
  }

  return new ApiError(message, code, response.status, requestId)
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  { anonymous = false }: { anonymous?: boolean } = {},
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(anonymous ? {} : await authHeaders()),
        ...init.headers,
      },
    })
  } catch (cause) {
    // fetch rejects only on network failure. On the free tier the likeliest
    // cause is the backend waking from sleep, which takes about a minute.
    throw new ApiError(
      'Could not reach the server. It may be waking up — try again in a moment.',
      'network',
      0,
    )
  }

  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  put: <T>(path: string) => request<T>(path, { method: 'PUT' }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),

  /**
   * A POST sent without a token, for the one thing a person does before they
   * have one: signing up. Separate and explicit rather than a flag on `post`,
   * so an authenticated call cannot lose its token by accident.
   */
  postAnonymous: <T>(path: string, body: unknown) =>
    request<T>(
      path,
      { method: 'POST', body: JSON.stringify(body) },
      { anonymous: true },
    ),

  /**
   * The base URL, for the one request that cannot go through `fetch` here:
   * starting a run, which streams and needs its own reader.
   */
  baseUrl: env.apiBaseUrl,
  authHeaders,
}
