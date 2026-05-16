import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import Dashboard from './pages/Dashboard';
import Backtest from './pages/Backtest';
import Scanner from './pages/Scanner';
import Portfolio from './pages/Portfolio';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/"          element={<Dashboard />} />
          <Route path="/backtest"  element={<Backtest />} />
          <Route path="/scanner"   element={<Scanner />} />
          <Route path="/portfolio" element={<Portfolio />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
