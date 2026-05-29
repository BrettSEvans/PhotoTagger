export interface NavButtonProps {
  label: string;
  isActive: boolean;
  onClick: () => void;
}

export function NavButton({ label, isActive, onClick }: NavButtonProps) {
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
