import { StrictMode, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeInit />
      <App />
    </BrowserRouter>
  </StrictMode>,
)
