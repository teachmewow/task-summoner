import { Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface DropdownOption<T extends string> {
  value: T;
  label: string;
  hint?: string;
}

interface DropdownProps<T extends string> {
  label?: string;
  value: T;
  options: DropdownOption<T>[];
  onChange: (value: T) => void;
  placeholder?: string;
  id?: string;
}

export function Dropdown<T extends string>({
  label,
  value,
  options,
  onChange,
  placeholder,
  id,
}: DropdownProps<T>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerId = id ?? `dropdown-${Math.random().toString(36).slice(2, 8)}`;

  useEffect(() => {
    if (!open) return;
    const onDocClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const current = options.find((o) => o.value === value);

  return (
    <div className="space-y-1" ref={rootRef}>
      {label ? (
        <label htmlFor={triggerId} className="block text-sm font-medium text-ghost">
          {label}
        </label>
      ) : null}
      <div className="relative">
        <button
          id={triggerId}
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center justify-between gap-2 rounded-md border border-rune-line-strong bg-vault-soft px-3 py-2 text-left text-sm text-ghost transition hover:border-arcane/50 focus:border-arcane focus:outline-none focus:ring-2 focus:ring-arcane/40"
        >
          <span className={current ? "" : "text-ghost-dimmer"}>
            {current?.label ?? placeholder ?? "—"}
          </span>
          <ChevronDown
            size={14}
            strokeWidth={2}
            className={[
              "shrink-0 text-ghost-dim transition-transform",
              open ? "rotate-180" : "",
            ].join(" ")}
          />
        </button>

        {open ? (
          <div className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-rune-line-strong bg-obsidian-raised p-1 shadow-[0_12px_40px_rgba(5,7,17,0.55)] backdrop-blur-sm">
            {options.length === 0 ? (
              <p className="px-3 py-2 text-xs text-ghost-dimmer">No options.</p>
            ) : (
              options.map((opt) => {
                const selected = opt.value === value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => {
                      onChange(opt.value);
                      setOpen(false);
                    }}
                    className={[
                      "flex w-full items-start justify-between gap-3 rounded-[5px] px-2.5 py-1.5 text-left text-sm transition",
                      selected
                        ? "bg-arcane/20 text-ghost"
                        : "text-ghost/90 hover:bg-vault hover:text-ghost",
                    ].join(" ")}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{opt.label}</span>
                      {opt.hint ? (
                        <span className="block truncate text-xs text-ghost-dimmer">{opt.hint}</span>
                      ) : null}
                    </span>
                    {selected ? (
                      <Check size={14} strokeWidth={2.25} className="mt-0.5 text-arcane" />
                    ) : null}
                  </button>
                );
              })
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
