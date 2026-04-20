import { Link } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";

interface CardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  href?: string;
  comingSoon?: boolean;
}

export function Card({ icon: Icon, title, description, href, comingSoon = false }: CardProps) {
  const body = (
    <div
      className={[
        "group relative flex h-full flex-col gap-3 rounded-lg border bg-vault-soft p-5 transition",
        comingSoon
          ? "cursor-not-allowed border-rune-line opacity-50"
          : "border-rune-line-strong hover:-translate-y-0.5 hover:border-arcane/60 hover:bg-vault hover:glow-arcane-soft",
      ].join(" ")}
    >
      <div className="flex items-center justify-between">
        <span
          className={[
            "inline-flex h-9 w-9 items-center justify-center rounded-md border",
            comingSoon
              ? "border-rune-line text-ghost-dim"
              : "border-rune-line-strong bg-obsidian-raised text-arcane",
          ].join(" ")}
        >
          <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
        </span>
        {comingSoon ? (
          <span className="rounded-full border border-rune-line-strong bg-obsidian-raised px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-ghost-dim">
            Coming soon
          </span>
        ) : null}
      </div>
      <div className="space-y-1">
        <h3 className="text-base font-semibold text-ghost">{title}</h3>
        <p className="text-sm text-ghost/80">{description}</p>
      </div>
    </div>
  );

  if (comingSoon || !href) {
    return (
      <div data-card data-kind="placeholder" aria-disabled="true">
        {body}
      </div>
    );
  }

  return (
    <Link to={href} data-card data-kind="active" className="block h-full">
      {body}
    </Link>
  );
}
