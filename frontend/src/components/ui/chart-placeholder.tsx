export function ChartPlaceholder({ title, caption }: { title: string; caption: string }) {
  const bars = [42, 55, 48, 72, 66, 88, 80, 94, 74, 86, 98, 91];

  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="text-sm text-[#a0a7b4]">{caption}</p>
        </div>
      </div>
      <div className="flex h-64 items-end gap-2 rounded border border-[#2d333d] bg-[#111419] p-4">
        {bars.map((bar, index) => (
          <div
            key={index}
            className="min-w-0 flex-1 rounded-t bg-gradient-to-t from-emerald-500/35 to-cyan-300/80"
            style={{ height: `${bar}%` }}
          />
        ))}
      </div>
    </div>
  );
}

