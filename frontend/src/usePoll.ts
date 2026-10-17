import { useEffect, useRef, useState } from 'react'

/** Polls `fetcher` every `intervalMs` and keeps the latest result in state.
 * Pass `key` when the fetcher's inputs change (e.g. a date range) to refetch immediately. */
export function usePoll<T>(fetcher: () => Promise<T>, intervalMs = 10_000, key?: unknown) {
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
  }, [intervalMs, key])

  return { data, error, refresh: () => fetcherRef.current().then(setData), set: setData }
}
