import { useState } from 'react';
import { InventoryPage } from './pages/InventoryPage';
import { DeployPage } from './pages/DeployPage';
import type { Page } from './components/Nav';

export default function App() {
  const [page, setPage] = useState<Page>('inventory');

  return page === 'deploy'
    ? <DeployPage page={page} onNavigate={setPage} />
    : <InventoryPage page={page} onNavigate={setPage} />;
}
