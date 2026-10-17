import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'
import { WidgetPanel } from './WidgetPanel'

// Follow the system theme; the panel has no toggle of its own.
const dark = window.matchMedia('(prefers-color-scheme: dark)')
const apply = () => document.documentElement.classList.toggle('dark', dark.matches)
apply()
dark.addEventListener('change', apply)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <WidgetPanel />
  </StrictMode>,
)
