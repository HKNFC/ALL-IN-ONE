import { useQuery } from "@tanstack/react-query";
import { fetchAnalysts } from "../api";
import { Twitter, Youtube, Users } from "lucide-react";

function initials(name: string) {
  return name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase();
}

export default function AnalystPanel() {
  const { data: analysts } = useQuery({
    queryKey: ["analysts"],
    queryFn: fetchAnalysts,
    staleTime: Infinity,
  });

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <Users className="w-5 h-5 text-amber-400" />
        <h2 className="text-white font-semibold">Takip Edilecek Analistler</h2>
      </div>
      <div className="space-y-3">
        {analysts?.map((analyst) => (
          <div
            key={analyst.id}
            className="bg-slate-800/60 border border-slate-700 hover:border-slate-600 rounded-xl p-4 transition-all"
          >
            <div className="flex items-start gap-3">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-sm flex-shrink-0"
                style={{ backgroundColor: analyst.avatar_color + "33", border: `1px solid ${analyst.avatar_color}55` }}
              >
                <span style={{ color: analyst.avatar_color }}>{initials(analyst.name)}</span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-white font-semibold text-sm">{analyst.name}</p>
                <p className="text-xs font-medium mt-0.5" style={{ color: analyst.avatar_color }}>{analyst.expertise}</p>
                <p className="text-slate-400 text-xs mt-1 leading-relaxed">{analyst.description}</p>
                <div className="flex items-center gap-2 mt-2">
                  {analyst.twitter && analyst.twitter !== "https://twitter.com/" && (
                    <a
                      href={analyst.twitter}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs text-slate-400 hover:text-blue-400 transition-colors"
                    >
                      <Twitter className="w-3.5 h-3.5" />
                      Twitter
                    </a>
                  )}
                  {analyst.youtube && (
                    <a
                      href={analyst.youtube}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs text-slate-400 hover:text-red-400 transition-colors"
                    >
                      <Youtube className="w-3.5 h-3.5" />
                      YouTube
                    </a>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
