import type { InputHTMLAttributes } from "react";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
}

export function Field({ label, hint, id, ...props }: FieldProps) {
  const inputId = id ?? `field-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <label htmlFor={inputId} className="block space-y-1">
      <span className="text-sm font-medium text-ghost-white">{label}</span>
      <input
        id={inputId}
        {...props}
        className="w-full rounded-md border border-shadow-purple/60 bg-void-900/60 px-3 py-2 text-sm text-ghost-white placeholder:text-soul-cyan/40 focus:border-arise-violet focus:outline-none focus:ring-2 focus:ring-arise-violet/40"
      />
      {hint ? <span className="block text-xs text-soul-cyan/70">{hint}</span> : null}
    </label>
  );
}

interface SegmentedProps<T extends string> {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: SegmentedProps<T>) {
  return (
    <div className="space-y-1">
      <span className="text-sm font-medium text-ghost-white">{label}</span>
      <div className="inline-flex rounded-md border border-shadow-purple/60 bg-void-900/60 p-0.5">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={[
              "rounded-[5px] px-3 py-1 text-xs font-medium transition",
              value === opt.value
                ? "bg-arise-violet/20 text-ghost-white shadow-[0_0_0_1px_rgba(168,85,247,0.5)]"
                : "text-soul-cyan/80 hover:text-ghost-white",
            ].join(" ")}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
