import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Navbar from './components/Navbar';
import Dashboard from './pages/Dashboard';
import DealDetail from './pages/DealDetail';
import Pipeline from './pages/Pipeline';
import SearchPage from './pages/Search.tsx';
import Search from './pages/Search.jsx';
import Watchlist from './pages/Watchlist';

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-deaven-bg">
        <Navbar />
        <main>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/search/area" element={<Search />} />
            <Route path="/deals/:id" element={<DealDetail />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
