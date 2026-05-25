import type React from "react";

type IconProps = { size?: number; className?: string };

function SvgIcon({ size = 20, className = "", children, viewBox = "0 0 24 24" }: IconProps & { children: React.ReactNode; viewBox?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function IconChat(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <path d="M8 9h8" />
      <path d="M8 13h6" />
    </SvgIcon>
  );
}

export function IconQuiz(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      <path d="M15 5.5 18.5 9" />
    </SvgIcon>
  );
}

export function IconAgents(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <rect x="3" y="3" width="18" height="18" rx="3" />
      <circle cx="9" cy="10" r="1.5" />
      <circle cx="15" cy="10" r="1.5" />
      <path d="M9 15c.83.67 2 1 3 1s2.17-.33 3-1" />
    </SvgIcon>
  );
}

export function IconLibrary(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
      <path d="M12 6v12" />
      <path d="M8 9h8" />
      <path d="M8 13h6" />
    </SvgIcon>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
      <path d="M11 3v2" />
      <path d="M3 11h2" />
      <path d="M5.6 5.6l1.4 1.4" />
      <path d="M16.4 5.6l-1.4 1.4" />
    </SvgIcon>
  );
}

export function IconGraph(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <circle cx="12" cy="5" r="2" />
      <circle cx="6" cy="19" r="2" />
      <circle cx="18" cy="12" r="2" />
      <path d="M12 7v3" />
      <path d="M11 16.5 7.5 18" />
      <path d="M16.5 13.5 14 15.5" />
    </SvgIcon>
  );
}

export function IconDashboard(props: IconProps) {
  return (
    <SvgIcon {...props}>
      <path d="M3 3v18h18" />
      <path d="M7 16h2" />
      <path d="M7 11h5" />
      <path d="M7 6h8" />
      <path d="M18 8l3 3-3 3" />
    </SvgIcon>
  );
}

export function IconGraduation(props: IconProps) {
  return (
    <SvgIcon {...props} viewBox="0 0 24 24">
      <path d="M22 10.5V6L12 1 2 6l10 5 8-4" />
      <path d="M6 10v3c0 3 3 6 6 6s6-3 6-6v-3" />
      <path d="M22 10.5V17" />
    </SvgIcon>
  );
}
