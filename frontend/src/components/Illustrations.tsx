interface Props {
  className?: string
}

export function IdleIllustration({ className }: Props) {
  return (
    <svg viewBox="0 0 240 180" className={className} fill="none" aria-hidden="true">
      <ellipse cx="120" cy="160" rx="82" ry="10" fill="var(--surface-2)" />
      <rect x="62" y="22" width="104" height="132" rx="14" fill="var(--surface)" stroke="var(--line-strong)" strokeWidth="2" />
      <rect x="78" y="42" width="34" height="34" rx="17" fill="var(--brand-soft)" />
      <circle cx="95" cy="55" r="6" fill="var(--brand-text)" />
      <path d="M84 70c2-6 8-8 11-8s9 2 11 8" stroke="var(--brand-text)" strokeWidth="2.5" strokeLinecap="round" />
      <rect x="120" y="46" width="32" height="7" rx="3.5" fill="var(--line-strong)" />
      <rect x="120" y="60" width="22" height="7" rx="3.5" fill="var(--line)" />
      <rect x="78" y="92" width="74" height="7" rx="3.5" fill="var(--line)" />
      <rect x="78" y="106" width="64" height="7" rx="3.5" fill="var(--line)" />
      <rect x="78" y="120" width="48" height="7" rx="3.5" fill="var(--line)" />
      <circle cx="162" cy="118" r="26" fill="var(--surface)" stroke="var(--brand)" strokeWidth="4" />
      <path d="M181 137l22 22" stroke="var(--brand)" strokeWidth="7" strokeLinecap="round" />
      <path d="M150 119l8 8 15-17" stroke="var(--ok)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="40" cy="48" r="4" fill="var(--brand-soft)" />
      <circle cx="204" cy="42" r="6" fill="var(--brand-soft)" />
      <path d="M198 78l3 6 6 3-6 3-3 6-3-6-6-3 6-3z" fill="var(--brand-text)" opacity="0.5" />
    </svg>
  )
}

export function NoResultIllustration({ className }: Props) {
  return (
    <svg viewBox="0 0 240 180" className={className} fill="none" aria-hidden="true">
      <ellipse cx="120" cy="160" rx="84" ry="10" fill="var(--surface-2)" />
      <rect x="44" y="34" width="152" height="108" rx="14" fill="var(--surface)" stroke="var(--line-strong)" strokeWidth="2" />
      <rect x="60" y="52" width="60" height="9" rx="4.5" fill="var(--line-strong)" />
      <rect x="60" y="70" width="112" height="7" rx="3.5" fill="var(--line)" />
      <rect x="60" y="84" width="96" height="7" rx="3.5" fill="var(--line)" />
      <rect x="60" y="98" width="104" height="7" rx="3.5" fill="var(--line)" />
      <circle cx="150" cy="112" r="30" fill="var(--surface)" stroke="var(--warn)" strokeWidth="4" />
      <path d="M170 134l24 24" stroke="var(--warn)" strokeWidth="7" strokeLinecap="round" />
      <path d="M139 101l22 22M161 101l-22 22" stroke="var(--warn)" strokeWidth="4" strokeLinecap="round" />
      <circle cx="30" cy="70" r="5" fill="var(--warn-soft)" />
      <circle cx="214" cy="56" r="4" fill="var(--warn-soft)" />
    </svg>
  )
}

export function ErrorIllustration({ className }: Props) {
  return (
    <svg viewBox="0 0 240 180" className={className} fill="none" aria-hidden="true">
      <ellipse cx="120" cy="160" rx="84" ry="10" fill="var(--surface-2)" />
      <path
        d="M120 24l86 118a8 8 0 0 1-6.5 12.7h-159A8 8 0 0 1 34 142z"
        fill="var(--bad-soft)"
        stroke="var(--bad)"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path d="M120 70v40" stroke="var(--bad)" strokeWidth="8" strokeLinecap="round" />
      <circle cx="120" cy="130" r="5.5" fill="var(--bad)" />
      <path d="M52 52l8 8M60 52l-8 8" stroke="var(--line-strong)" strokeWidth="3" strokeLinecap="round" />
      <path d="M186 74c4 0 7 3 7 7s-3 7-7 7" stroke="var(--line-strong)" strokeWidth="3" strokeLinecap="round" />
      <circle cx="40" cy="116" r="4" fill="var(--bad-soft)" />
    </svg>
  )
}
