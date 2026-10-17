import { StrictMode, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { api } from '@/api/client'
import { setHome } from '@/format'

function ThemeInit() {
  useEffect(() => {
    try {
      if (localStorage.getItem('theme') === 'dark') document.documentElement.classList.add('dark')
    } catch {
      /* ignore */
    }
  }, [])
  return null
}

function render() {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <BrowserRouter>
        <ThemeInit />
        <App />
      </BrowserRouter>
    </StrictMode>,
  )
}

// Learn the home directory first so paths render as ~/...; render anyway if the backend is down.
api
  .meta()
  .then((m) => setHome(m.home))
  .catch(() => {})
  .finally(render)
