// src/components/SearchBar.tsx
import React, { useState, useEffect, useRef } from "react";
import { search } from "../api/index";
import { Link } from "react-router-dom";
import { SearchInput } from "./ui/SearchInput";

type ResultSet = {
  artists?: any[];
  albums?: any[];
  tracks?: any[];
};

function useDebounce<T>(value: T, delay = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setV(value), delay);
    return () => clearTimeout(h);
  }, [value, delay]);
  return v;
}

export default function SearchBar({ placeholder = "Search music..." }: { placeholder?: string }) {
  const [q, setQ] = useState("");
  const debouncedQ = useDebounce(q, 400);
  const [results, setResults] = useState<ResultSet>({});
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!debouncedQ || debouncedQ.trim().length < 2) {
      setResults({});
      setLoading(false);
      return;
    }
    setLoading(true);
    let cancelled = false;
    (async () => {
      try {
        const r = await search(debouncedQ.trim());
        if (!cancelled) {
          setResults(r || {});
          setOpen(true);
          setLoading(false);
        }
      } catch (e) {
        console.error("Search error", e);
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [debouncedQ]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("click", onDoc);
    return () => document.removeEventListener("click", onDoc);
  }, []);

  const anyResults = (results.artists?.length || 0) + (results.albums?.length || 0) + (results.tracks?.length || 0);

  return (
    <div className="relative w-full max-w-2xl" ref={ref}>
      <SearchInput
        value={q}
        onChange={setQ}
        placeholder={placeholder}
        onFocus={() => debouncedQ && setOpen(true)}
        size="md"
        loading={loading}
      />

      {/* Results dropdown */}
      {open && debouncedQ && (
        <div className="absolute z-50 mt-2 w-full glass rounded-2xl shadow-2xl border-slate-200 dark:border-white/10 max-h-[32rem] overflow-auto">
          {anyResults ? (
            <div className="divide-y divide-slate-200 dark:divide-white/10">
              {/* Artists */}
              {results.artists && results.artists.length > 0 && (
                <div className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-2xl">🎤</span>
                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Artists</h3>
                  </div>
                  <div className="space-y-1">
                    {results.artists.slice(0, 6).map((a: any) => (
                      <Link
                        key={a.id || a.name}
                        to={`/artists/${encodeURIComponent(String(a.id || a.browseId || a.name))}`}
                        onClick={() => setOpen(false)}
                        className="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-200 group"
                      >
                        {a.thumbnails?.[0]?.url ? (
                          <img 
                            src={a.thumbnails[0].url} 
                            className="w-12 h-12 rounded-full object-cover bg-slate-200 dark:bg-zinc-800 group-hover:scale-105 transition-transform" 
                            alt={a.name}
                          />
                        ) : (
                          <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 dark:from-red-600 dark:to-red-800 flex items-center justify-center text-white font-bold">
                            {a.name?.[0]?.toUpperCase()}
                          </div>
                        )}
                        <span className="text-sm font-medium text-foreground group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors">
                          {a.name || a.title}
                        </span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}

              {/* Albums */}
              {results.albums && results.albums.length > 0 && (
                <div className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-2xl">💿</span>
                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Albums</h3>
                  </div>
                  <div className="space-y-1">
                    {results.albums.slice(0, 8).map((al: any) => (
                      <Link
                        key={al.id || al.playlistId || al.title}
                        to={`/albums/${encodeURIComponent(String(al.id || al.playlistId || al.title))}`}
                        onClick={() => setOpen(false)}
                        className="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-200 group"
                      >
                        {al.thumbnails?.[0]?.url ? (
                          <img 
                            src={al.thumbnails[0].url} 
                            className="w-12 h-12 rounded-lg object-cover bg-slate-200 dark:bg-zinc-800 group-hover:scale-105 transition-transform" 
                            alt={al.title}
                          />
                        ) : (
                          <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-slate-200 to-slate-300 dark:from-zinc-800 dark:to-zinc-900" />
                        )}
                        <span className="text-sm font-medium text-foreground group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors">
                          {al.title}
                        </span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}

              {/* Tracks */}
              {results.tracks && results.tracks.length > 0 && (
                <div className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-2xl">🎵</span>
                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Tracks</h3>
                  </div>
                  <div className="space-y-1">
                    {results.tracks.slice(0, 10).map((t: any) => (
                      <Link
                        key={t.id || t.videoId || t.title}
                        to={`/tracks/${encodeURIComponent(String(t.id || t.videoId))}`}
                        onClick={() => setOpen(false)}
                        className="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-200 group"
                      >
                        {t.thumbnails?.[0]?.url ? (
                          <img 
                            src={t.thumbnails[0].url} 
                            className="w-12 h-12 rounded-lg object-cover bg-slate-200 dark:bg-zinc-800 group-hover:scale-105 transition-transform" 
                            alt={t.title}
                          />
                        ) : (
                          <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-slate-200 to-slate-300 dark:from-zinc-800 dark:to-zinc-900" />
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-foreground group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors truncate">
                            {t.title}
                          </div>
                          {t.artists && (
                            <div className="text-xs text-muted-foreground truncate">
                              {(t.artists || []).join(", ")}
                            </div>
                          )}
                        </div>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="p-8 text-center">
              <div className="text-4xl mb-3">🔍</div>
              <p className="text-sm text-muted-foreground">No results found</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}