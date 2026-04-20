import { Link } from "@tanstack/react-router";
import { AlertTriangle } from "lucide-react";
import { useConfigStatus } from "~/lib/config";

export function SetupBanner() {
  const { data } = useConfigStatus();
  if (!data || data.configured) return null;
  return (
    <div className="border-b border-ember/30 bg-ember/10 text-ember">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-2 text-sm">
        <span className="flex items-center gap-2">
          <AlertTriangle size={16} strokeWidth={2} />
          Task Summoner is not configured.
        </span>
        <Link to="/setup" className="font-medium underline hover:text-ember/80">
          Go to /setup
        </Link>
      </div>
    </div>
  );
}
