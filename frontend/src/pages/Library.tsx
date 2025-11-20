// frontend/src/pages/Library.tsx
import React, { useEffect, useState } from "react";
import { getArtists, getArtist } from "../lib/api";

function pickThumbnailFrom(thumbs: any): string | null {
  if (!thumbs) return null;
  if (Array.isArray(thumbs)) {
    for (let i = thumbs.length - 1; i >= 0; i--) {
      const t = thumbs[i];
      if (!t) continue;
      if (typeof t === "string") return t;
      if (typeof t === "object") {
        if (t.url) return t.url;
        if (t.thumbnailUrl) return t.thumbnailUrl;
      }
    }
    return null;
  }
  if (typeof thumbs === "string") return thumbs;
  if (typeof thumbs === "object" && thumbs.url) return thumbs.url;
  return null;
}

export default function Library(): JSX.Element {
  const [albums, setAlbums] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const artists = (await getArtists()) || [];
        // récupérer albums pour chaque artiste (en parallèle)
        const prom = artists.map(async (a: any) => {
          try {
            const res = await getArtist(String(a.id));
            // res = { artist: {...}, albums: [...] }
            const artistName = res?.artist?.name ?? a.name ?? "unknown";
            const albumList: any[] = res?.albums ?? [];
            return albumList.map((al: any) => ({
              id: al.id,
              title: al.title,
              artist: artistName,
              thumbnails: al.thumbnails,
              playlist_id: al.playlist_id,
              year: al.year,
            }));
          } catch (e) {
            // ignore single-artist failure
            return [];
          }
        });

        const nested = await Promise.all(prom);
        const flat = nested.flat();
        if (mounted) {
          setAlbums(flat);
        }
      } catch (e: any) {
        console.error(e);
        if (mounted) setError(String(e?.message ?? e));
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) return <div>Chargement…</div>;
  if (error) return <div className="text-red-600">Erreur: {error}</div>;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Bibliothèque</h1>

      {albums.length === 0 && <div>Aucun album trouvé.</div>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {albums.map((a) => {
          const thumb = pickThumbnailFrom(a.thumbnails) ?? "/assets/placeholder-album.png";
          return (
            <div key={String(a.id)} className="bg-white rounded shadow p-3">
              <img
                src={thumb}
                alt={a.title}
                className="w-full h-40 object-cover rounded"
              />
              <h3 className="mt-2 font-semibold">{a.title}</h3>
              <p className="text-sm text-gray-600">{a.artist}</p>
              {a.year && <div className="text-xs text-gray-400">{a.year}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}