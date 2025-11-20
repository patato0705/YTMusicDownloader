import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { search as apiSearch } from "../lib/api";
import MediaCard from "../components/MediaCard";
import { formatArtist, formatAlbum, formatTrack } from "../lib/mediaHelpers";

type AnyObj = Record<string, any>;

export default function Browse(): JSX.Element {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<{ artists: AnyObj[]; albums: AnyObj[]; tracks: AnyObj[] }>({
    artists: [],
    albums: [],
    tracks: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const debounceRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, []);

  // Normalize backend response into grouped shape { artists, albums, tracks }
  const normalizeResponse = (raw: any) => {
    const out = { artists: [] as AnyObj[], albums: [] as AnyObj[], tracks: [] as AnyObj[] };

    if (!raw) return out;

    // If backend already returns grouped object
    if (typeof raw === "object" && !Array.isArray(raw)) {
      // try common keys
      const artists = raw.artists ?? raw.artists_list ?? raw.artist ?? [];
      const albums = raw.albums ?? raw.albums_list ?? raw.album ?? [];
      const tracks = raw.tracks ?? raw.songs ?? raw.songs_list ?? raw.track ?? [];

      if (Array.isArray(artists) || Array.isArray(albums) || Array.isArray(tracks)) {
        out.artists = Array.isArray(artists) ? artists : [];
        out.albums = Array.isArray(albums) ? albums : [];
        out.tracks = Array.isArray(tracks) ? tracks : [];
        return out;
      }
      // if not arrays, fall through and try to interpret as flat list
    }

    // If backend returned a flat array of normalized items
    const list = Array.isArray(raw) ? raw : [];

    for (const it of list) {
      if (!it || typeof it !== "object") continue;

      // result kind may live in several keys
      const kindRaw =
        (it.resultType ?? it.type ?? it.result_type ?? (it.raw && (it.raw.resultType ?? it.raw.type))) || "";
      const kind = String(kindRaw).toLowerCase();

      if (kind === "artist") {
        out.artists.push(it);
      } else if (kind === "album") {
        out.albums.push(it);
      } else if (kind === "song" || kind === "track") {
        out.tracks.push(it);
      } else {
        // heuristics: if has videoId or duration -> treat as track
        if (it.videoId || it.duration || it.duration_seconds) {
          out.tracks.push(it);
        } else if (it.browseId && String(it.browseId).startsWith("MPRE")) {
          // albums sometimes use MPRE* browseId heuristics — treat as album
          out.albums.push(it);
        } else if (it.artists || it.artist) {
          // if artist-like fields and no explicit kind
          out.artists.push(it);
        } else {
          // unknowns: ignore for now
        }
      }
    }

    return out;
  };

  const doSearch = async (rawQuery: string) => {
    const qtrim = rawQuery.trim();
    if (!qtrim) {
      setResults({ artists: [], albums: [], tracks: [] });
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const r = await apiSearch(rawQuery, undefined, 10);
      // backend might return array or grouped object
      const grouped = normalizeResponse(r);
      setResults(grouped);
    } catch (e: any) {
      console.error("Search error", e);
      setError(e?.message ? String(e.message) : "Search failed");
      setResults({ artists: [], albums: [], tracks: [] });
    } finally {
      setLoading(false);
    }
  };

  const onChange = (v: string) => {
    setQ(v);
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      doSearch(v);
    }, 300);
  };

  const onSubmit = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    doSearch(q);
  };

  const onSelectArtist = (id: string) => {
    navigate(`/artists/${encodeURIComponent(id)}`);
  };

  const onSelectAlbum = (id: string) => {
    navigate(`/albums/${encodeURIComponent(id)}`);
  };

  const onSelectTrack = (albumid: string) => {
    navigate(`/albums/${encodeURIComponent(albumid)}`);
  };

  const hasAny = results.artists.length + results.albums.length + results.tracks.length > 0;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Browse</h1>
      <form onSubmit={onSubmit} className="mb-6">
        <div className="max-w-3xl">
          <label className="block">
            <div className="flex gap-2">
              <input
                value={q}
                onChange={(e) => onChange(e.target.value)}
                placeholder="Rechercher artistes, albums, titres..."
                className="flex-1 rounded-md border px-3 py-2 focus:outline-none focus:ring"
              />
              <button
                type="submit"
                className="px-3 py-2 rounded-md bg-blue-600 text-white disabled:opacity-60"
                disabled={loading}
              >
                {loading ? "Recherche…" : "Rechercher"}
              </button>
            </div>
          </label>
        </div>
      </form>

      {error && <div className="mb-4 text-red-600">Erreur : {error}</div>}

      {!q.trim() && <div className="text-sm text-gray-600">Tapez quelque chose pour lancer une recherche.</div>}

      {q.trim() && !hasAny && !loading && <div className="text-sm text-gray-600">Aucun résultat.</div>}

      <div className="space-y-8 mt-4">
        {/* Artists */}
        {results.artists.length > 0 && (
          <section>
            <h2 className="text-xl font-semibold mb-3">Artistes</h2>
            <div className="flex gap-4 overflow-x-auto pb-4">
              {results.artists.map((a) => {
                const formatted = formatArtist(a);
                return (
                  <MediaCard
                    key={formatted.id}
                    {...formatted}
                    onClick={() => onSelectArtist(formatted.id)}
                  />
                );
              })}
            </div>
          </section>
        )}

        {/* Albums */}
        {results.albums.length > 0 && (
          (() => {
            const albumsOnly = results.albums.filter((al: any) => {
              const t = (al.type ?? al.resultType ?? "").toString().toLowerCase();
              return !t || !(t.includes("playlist") || t.includes("mix"));
            });
            return albumsOnly.length > 0 ? (
              <section>
                <h2 className="text-xl font-semibold mb-3">Albums</h2>
                <div className="flex gap-4 overflow-x-auto pb-4">
                  {albumsOnly.map((al) => {
                    const formatted = formatAlbum(al);
                    return (
                      <MediaCard
                        key={formatted.id}
                        {...formatted}
                        onClick={() => onSelectAlbum(formatted.id)}
                      />
                    );
                  })}
                </div>
              </section>
            ) : null;
          })()
        )}

        {/* Tracks */}
        {results.tracks.length > 0 && (
          <section>
            <h2 className="text-xl font-semibold mb-3">Titres</h2>
            <div className="flex gap-4 overflow-x-auto pb-4">
              {results.tracks.map((t) => {
                const formatted = formatTrack(t);
                const albumId = t.album?.id || "";
                return (
                  <MediaCard
                    key={formatted.id}
                    {...formatted}
                    onClick={() => onSelectTrack(albumId)}
                  />
                );
              })}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}