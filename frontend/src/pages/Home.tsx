import React, { useEffect, useState } from "react";
import { getArtists } from "../lib/api";
import { Link } from "react-router-dom";

function pickThumbnail(thumbs: any): string | null {
  if (!thumbs) return null;
  // thumbs may be an array of strings or dicts, or a single string/dict
  if (Array.isArray(thumbs)) {
    // prefer last element with a url or string
    for (let i = thumbs.length - 1; i >= 0; i--) {
      const t = thumbs[i];
      if (!t) continue;
      if (typeof t === "string") return t;
      if (typeof t === "object" && t.url) return t.url;
    }
    return null;
  }
  if (typeof thumbs === "string") return thumbs;
  if (typeof thumbs === "object" && thumbs.url) return thumbs.url;
  return null;
}

export default function Home(): JSX.Element {
  const [artists, setArtists] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    getArtists()
      .then((res: any) => {
        if (!mounted) return;
        // backend returns list of artist dicts
        setArtists(Array.isArray(res) ? res : []);
      })
      .catch((e: any) => {
        if (!mounted) return;
        setError(String(e?.message ?? e));
      })
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Bienvenue</h1>

      <p className="mb-4">
        Utilise le menu pour parcourir ta bibliothèque ou lancer un téléchargement.
      </p>

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Artistes</h2>
          <div className="text-sm text-gray-500">{loading ? "Chargement…" : `${artists.length} trouvés`}</div>
        </div>

        {error && <div className="text-red-600 mb-3">Erreur: {error}</div>}

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {loading && (
            <>
              <div className="p-4 bg-white rounded shadow animate-pulse h-28" />
              <div className="p-4 bg-white rounded shadow animate-pulse h-28" />
              <div className="p-4 bg-white rounded shadow animate-pulse h-28" />
            </>
          )}

          {!loading && artists.length === 0 && <div>Aucun artiste enregistré.</div>}

          {!loading &&
            artists.map((a) => {
              const thumb = pickThumbnail(a.thumbnails);
              return (
                <Link
                  to={`/artists/${encodeURIComponent(String(a.id))}`}
                  key={String(a.id)}
                  className="bg-white rounded-xl shadow-sm p-3 flex gap-3 items-center hover:shadow-md transition-shadow"
                >
                  <img
                    src={thumb ?? "/assets/placeholder-artist.png"}
                    alt={a.name ?? "artist"}
                    className="w-16 h-16 object-cover rounded-md bg-gray-100"
                  />
                  <div className="flex-1">
                    <div className="font-semibold text-gray-900">{a.name}</div>
                    <div className="text-sm text-gray-500">{a.monitored ? "Monitored" : ""}</div>
                  </div>
                </Link>
              );
            })}
        </div>
      </section>
    </div>
  );
}