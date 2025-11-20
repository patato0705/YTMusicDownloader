// frontend/src/components/SearchBar.tsx
import React, { useState, useEffect, useRef } from "react";
import { search } from "../lib/api";
import { Link, useNavigate } from "react-router-dom";

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

export default function SearchBar({ placeholder = "Rechercher..." }: { placeholder?: string }) {
  const [q, setQ] = useState("");
  const debouncedQ = useDebounce(q, 400);
  const [results, setResults] = useState<ResultSet>({});
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    if (!debouncedQ || debouncedQ.trim().length < 2) {
      setResults({});
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const r = await search(debouncedQ.trim());
        if (!cancelled) {
          setResults(r || {});
          setOpen(true);
        }
      } catch (e) {
        console.error("Search error", e);
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
    <div className="relative" ref={ref}>
      <input
        value={q}
        onChange={(e) => { setQ(e.target.value); }}
        onFocus={() => debouncedQ && setOpen(true)}
        placeholder={placeholder}
        className="rounded-md border px-3 py-2 w-80"
        aria-label="search"
      />
      {open && debouncedQ && (
        <div className="absolute z-50 mt-1 w-96 bg-white border shadow-lg rounded-md max-h-96 overflow-auto">
          {anyResults ? (
            <div className="divide-y">
              {/* Artists */}
              {results.artists && results.artists.length > 0 && (
                <div className="p-2">
                  <div className="text-xs text-gray-500 uppercase font-semibold px-1">Artistes</div>
                  {results.artists.slice(0,6).map((a: any) => (
                    <div key={a.id || a.name} className="p-1 hover:bg-gray-50">
                      <Link to={`/artists/${encodeURIComponent(String(a.id || a.browseId || a.name))}`} onClick={() => setOpen(false)}>
                        <div className="flex items-center gap-2">
                          {a.thumbnails?.[0]?.url ? (
                            <img src={a.thumbnails[0].url} className="w-8 h-8 object-cover rounded" alt={a.name}/>
                          ) : null}
                          <div className="text-sm">{a.name || a.title}</div>
                        </div>
                      </Link>
                    </div>
                  ))}
                </div>
              )}

              {/* Albums */}
              {results.albums && results.albums.length > 0 && (
                <div className="p-2">
                  <div className="text-xs text-gray-500 uppercase font-semibold px-1">Albums</div>
                  {results.albums.slice(0,8).map((al: any) => (
                    <div key={al.id || al.playlistId || al.title} className="p-1 hover:bg-gray-50">
                      <Link to={`/albums/${encodeURIComponent(String(al.id || al.playlistId || al.title))}`} onClick={() => setOpen(false)}>
                        <div className="flex items-center gap-2">
                          {al.thumbnails?.[0]?.url ? <img src={al.thumbnails[0].url} className="w-8 h-8 object-cover rounded" alt={al.title}/> : null}
                          <div className="text-sm">{al.title}</div>
                        </div>
                      </Link>
                    </div>
                  ))}
                </div>
              )}

              {/* Tracks */}
              {results.tracks && results.tracks.length > 0 && (
                <div className="p-2">
                  <div className="text-xs text-gray-500 uppercase font-semibold px-1">Titres</div>
                  {results.tracks.slice(0,10).map((t: any) => (
                    <div key={t.id || t.videoId || t.title} className="p-1 hover:bg-gray-50">
                      <Link to={`/tracks/${encodeURIComponent(String(t.id || t.videoId))}`} onClick={() => setOpen(false)}>
                        <div className="flex items-center gap-2">
                          {t.thumbnails?.[0]?.url ? <img src={t.thumbnails[0].url} className="w-8 h-8 object-cover rounded" alt={t.title}/> : null}
                          <div className="text-sm">
                            <div>{t.title}</div>
                            {t.artists && <div className="text-xs text-gray-500">{(t.artists || []).join(", ")}</div>}
                          </div>
                        </div>
                      </Link>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="p-3 text-sm text-gray-500">Aucun résultat</div>
          )}
        </div>
      )}
    </div>
  );
}