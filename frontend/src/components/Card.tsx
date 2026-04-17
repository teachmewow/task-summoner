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
        "group relative flex h-full flex-col gap-3 rounded-lg border bg-void-800/70 p-5 transition",
        comingSoon
          ? "cursor-not-allowed border-shadow-purple/30 opacity-50"
          : "border-shadow-purple/60 hover:-translate-y-0.5 hover:border-arise-violet/70 hover:bg-void-700/70 hover:shadow-[0_0_32px_rgba(168,85,247,0.18)]",
      ].join(" ")}
    >
      <div className="flex items-center justify-between">
        <span
          className={[
            "inline-flex h-9 w-9 items-center justify-center rounded-md border",
            comingSoon
              ? "border-shadow-purple/40 text-soul-cyan/70"
              : "border-shadow-purple/70 bg-void-900/60 text-arise-violet-bright",
          ].join(" ")}
        >
          <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
        </span>
        {comingSoon ? (
          <span className="rounded-full border border-shadow-purple/60 bg-void-900/80 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-soul-cyan/80">
            Coming soon
          </span>
        ) : null}
      </div>
      <div className="space-y-1">
        <h3 className="text-base font-semibold text-ghost-white">{title}</h3>
        <p className="text-sm text-soul-cyan/80">{description}</p>
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
