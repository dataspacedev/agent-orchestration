export type Page = 'inventory' | 'deploy';

interface NavProps {
  current: Page;
  onNavigate: (page: Page) => void;
}

const tabs: { id: Page; label: string }[] = [
  { id: 'inventory', label: 'Inventory' },
  { id: 'deploy', label: 'Deploy' },
];

export function Nav({ current, onNavigate }: NavProps) {
  return (
    <nav className="flex gap-1">
      {tabs.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => onNavigate(id)}
          className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
            current === id
              ? 'bg-slate-700 text-white'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
