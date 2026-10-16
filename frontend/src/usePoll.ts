import { useEffect, useRef, useState } from 'react'

/** Polls `fetcher` every `intervalMs` and keeps the latest result in state.
 * This is the "live read" mechanism — no manual regenerate step needed. */
export function usePoll<T>(fetcher: () => Promise<T>, intervalMs = 10_000) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  useEffect(() => {
    let cancelled = false
    const tick = () => {
      fetcherRef.current()
        .then((d) => {
          if (!cancelled) {
            setData(d)
            setError(null)
          }
        })
        .catch((e) => {
          if (!cancelled) setError(String(e))
        })
    }
    tick()
    const id = setInterval(tick, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [intervalMs])

  return { data, error, refresh: () => fetcherRef.current().then(setData) }
}
