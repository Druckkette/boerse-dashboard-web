import clsx from "clsx";

const tones = {
  good: "border-[#b7e2cf] bg-[#eaf7ef] text-[#138a57]",
  neutral: "border-[#bdd3ff] bg-[#eef5ff] text-[#2563eb]",
  warning: "border-[#efd58f] bg-[#fff7df] text-[#9a650f]",
  bad: "border-[#f0b9b5] bg-[#fff0ef] text-[#c2413b]"
};

export function StatusChip({
  children,
  tone = "neutral"
}: {
  children: React.ReactNode;
  tone?: keyof typeof tones;
}) {
  return (
    <span className={clsx("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-4", tones[tone])}>
      {children}
    </span>
  );
}
