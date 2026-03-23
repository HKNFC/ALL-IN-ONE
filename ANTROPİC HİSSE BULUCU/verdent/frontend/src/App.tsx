import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import Dashboard from './pages/Dashboard'
import Backtest from './pages/Backtest'
import Scanner from './pages/Scanner'
import Portfolio from './pages/Portfolio'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="backtest" element={<Backtest />} />
          <Route path="scanner" element={<Scanner />} />
          <Route path="portfolio" element={<Portfolio />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
