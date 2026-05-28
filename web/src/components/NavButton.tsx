export interface NavButtonProps {
  label: string
  isActive: boolean
  onClick: () => void
}

export function NavButton({ label, isActive, onClick }: NavButtonProps) {
  return (
    <button
      onClick={onClick}
      aria-current={isActive ? 'page' : undefined}
      className={`px-4 py-4 font-medium transition-colors ${
        isActive
          ? 'text-blue-600 border-b-2 border-blue-600'
          : 'text-gray-600 hover:text-gray-900'
      }`}
    >
      {label}
    </button>
  )
}
