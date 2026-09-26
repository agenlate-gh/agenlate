'use client'

/**
 * Starts the backend waking the moment any page loads.
 *
 * The API runs on Render's free tier, which sleeps after fifteen idle minutes
 * and takes around fifty seconds to come back. Without this, the first request
 * a visitor makes — usually pressing Sign in — is the one that pays that wait.
 * Firing a request on load moves the wait to the seconds they spend reading
 * the page, which is time they were spending anyway.
 *
 * `no-cors` because the response is never read: this only has to reach the
 * server, and an opaque request cannot log a CORS error if the origin list is
 * ever wrong. That failure would then surface where it belongs, on a real
 * request.
 */

import { useEffect } from 'react'

import { env } from '@/lib/env'

export function WakeBackend() {
  useEffect(() => {
    fetch(`${env.apiBaseUrl}/health`, { mode: 'no-cors', cache: 'no-store' }).catch(
      () => {
        // Nothing to do. The request only exists to start the server; if it
        // fails, the next real request will say why.
      },
    )
  }, [])

  return null
}
