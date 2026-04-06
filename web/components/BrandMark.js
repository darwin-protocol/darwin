export default function BrandMark({ className = "", title = "Darwin coin mark" }) {
  return (
    <svg
      className={className}
      viewBox="0 0 128 128"
      role="img"
      aria-label={title}
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="darwin-shell" x1="18%" y1="16%" x2="82%" y2="86%">
          <stop offset="0%" stopColor="#1d5ccd" />
          <stop offset="58%" stopColor="#1242a4" />
          <stop offset="100%" stopColor="#0f2d67" />
        </linearGradient>
        <linearGradient id="darwin-orbit" x1="16%" y1="14%" x2="84%" y2="82%">
          <stop offset="0%" stopColor="#4fd7cb" />
          <stop offset="100%" stopColor="#0d7b73" />
        </linearGradient>
      </defs>
      <circle cx="64" cy="64" r="58" fill="#102540" />
      <circle cx="64" cy="64" r="50" fill="url(#darwin-shell)" />
      <circle cx="64" cy="64" r="35" fill="#f4efe5" />
      <path
        d="M43 34h17.5c19.6 0 32.5 12.2 32.5 30S80.1 94 60.5 94H43V34Zm16.2 47.5c11.6 0 19.1-6.4 19.1-17.5 0-11-7.5-17.5-19.1-17.5h-4.5v35h4.5Z"
        fill="#1546a0"
      />
      <path
        d="M22 61c3.4-15.2 13.7-27.2 28-32.6"
        fill="none"
        stroke="url(#darwin-orbit)"
        strokeLinecap="round"
        strokeWidth="7"
      />
      <circle cx="26" cy="62" r="4.8" fill="#f7a154" />
      <circle cx="35" cy="44" r="4.4" fill="#f7a154" />
      <circle cx="50" cy="31" r="4" fill="#f7a154" />
    </svg>
  );
}
