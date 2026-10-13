import type { SVGProps } from "react";

type VetoqMarkProps = SVGProps<SVGSVGElement> & {
  title?: string;
};

/**
 * The broken outer circuit represents an execution boundary. The inner
 * chevron is a locked goal and the copper node is the final verified action.
 */
export function VetoqMark({ className, title, ...props }: VetoqMarkProps) {
  const accessibleProps = title
    ? { "aria-label": title, role: "img" as const }
    : { "aria-hidden": true as const };

  return (
    <svg
      {...props}
      {...accessibleProps}
      className={["vetoq-mark", className].filter(Boolean).join(" ")}
      focusable="false"
      viewBox="0 0 48 48"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        className="vetoq-mark__boundary"
        d="M24 3.75 41.5 13.9v20.2L24 44.25 6.5 34.1V13.9L24 3.75Z"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.5"
      />
      <path
        className="vetoq-mark__goal"
        d="m14.25 17.5 9.75 15 9.75-15"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="4"
      />
      <path
        className="vetoq-mark__gate"
        d="M35.75 36.25h5.75v-5.75"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.5"
      />
      <circle className="vetoq-mark__proof" cx="39.25" cy="38.75" r="3" />
    </svg>
  );
}

export function VetoqWordmark({ className }: { className?: string }) {
  return (
    <span className={["vetoq-wordmark", className].filter(Boolean).join(" ")}>
      <VetoqMark />
      <span className="vetoq-wordmark__name">VETOQ</span>
    </span>
  );
}
