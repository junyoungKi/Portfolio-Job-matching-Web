/**
 * Author: Joonyoung Ki
 *
 * Application entry point.
 *
 * Loads the Pretendard font and global styles, then mounts the React ``App`` into ``#root``.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './components/AuthProvider.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
)
