import { useLocation } from 'react-router-dom'

export interface NavButtonProps {
  label: string;
  onClick: () => void;
}

export function NavButton({ label, onClick }: NavButtonProps) {
  const location = useLocation()
  const isActive = (() => {
    const path = location.pathname
    if (label.includes('Roster')) return path.startsWith('/roster')
    if (label.includes('Upload')) return path === '/upload'
    if (label.includes('Players')) return path.startsWith('/players') || path.startsWith('/player')
    if (label.includes('Search')) return path.startsWith('/search')
    if (label.includes('Gallery')) return path === '/gallery'
    return false
  })()

  return (
    <button
      onClick={onClick}
      aria-current={isActive ? 'page' : undefined}
      className={`
        px-5 py-2.5 my-1.5 rounded-full border-2 font-jakarta font-bold text-sm
        transition-all duration-200 ease-bounce
        ${isActive
          ? 'bg-accent text-white border-foreground shadow-pop -translate-x-px -translate-y-px'
          : 'bg-transparent text-foreground border-transparent hover:bg-tertiary hover:border-foreground'
        }
      `}
    >
      {label}
    </button>
  );
}
