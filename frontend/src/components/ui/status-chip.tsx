import clsx from "clsx";

const tones = {
  good: "border-emerald-400/35 bg-emerald-400/10 text-emerald-200",
  neutral: "border-sky-300/30 bg-sky-300/10 text-sky-100",
  warning: "border-amber-300/35 bg-amber-300/10 text-amber-100",
  bad: "border-rose-300/35 bg-rose-300/10 text-rose-100"
};

export function StatusChip({
  children,
  tone = "neutral"
}: {
  children: React.ReactNode;
  tone?: keyof typeof tones;
}) {
  return (
    <span className={clsx("inline-flex items-center rounded border px-2 py-1 text-xs", tones[tone])}>
      {children}
    </span>
  );
}

