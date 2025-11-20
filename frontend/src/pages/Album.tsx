import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getAlbum, postAlbumDownload } from "../lib/api";

export default function AlbumPage() {
  const { albumId } = useParams<{ albumId: string }>();
  const [albumData, setAlbumData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enqueuing, setEnqueuing] = useState(false);
  const [enqueueResult, setEnqueueResult] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!albumId) return;
    (async () => {
      try {
        const data = await getAlbum(albumId);
        setAlbumData(data);
      } catch (e: any) {
        console.error(e);
        setError(e.message || "Erreur lors de la récupération de l'album");
      } finally {
        setLoading(false);
      }
    })();
  }, [albumId]);

  if (loading) return <div className="text-center py-8">Chargement…</div>;
  if (error) return <div className="text-center py-8 text-red-500">Erreur : {error}</div>;
  if (!albumData) return <div className="text-center py-8">Album introuvable</div>;

  const album = albumData.album;
  const tracks = albumData.tracks || [];

  // Fonction pour formater la durée en minutes et secondes
  const formatDuration = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds < 10 ? '0' : ''}${remainingSeconds}`;
  };

  // Trouver la meilleure qualité de couverture
  const cover = album.thumbnail;

  // Extraire les informations de l'artiste
  const artistName = album.artist.name;
  const artistId = album.artist.id;

  const handleDownloadAlbum = async () => {
    if (!albumId) return;
    setEnqueuing(true);
    setEnqueueResult(null);
    try {
      const res = await postAlbumDownload(String(albumId));
      // res attendu: { enqueued: number, job_ids: number[], skipped: number }
      const enqueued = res?.enqueued ?? 0;
      const skipped = res?.skipped ?? 0;
      setEnqueueResult(`Jobs enqueued : ${enqueued}${skipped ? ` — skipped: ${skipped}` : ""}`);
    } catch (err: any) {
      console.error(err);
      setEnqueueResult(`Erreur lors de l'enqueue : ${err?.message || String(err)}`);
    } finally {
      setEnqueuing(false);
    }
  };

  return (
    <div className="p-4 md:p-8">
      <div className="flex flex-col md:flex-row gap-8">
        {/* Section gauche - Informations de l'album */}
        <div className="w-full md:w-1/3 bg-white rounded-lg shadow-md p-6">
          <div className="mb-6">
            {cover ? (
              <img
                src={cover}
                alt={album.title}
                className="w-full h-auto rounded-lg"
              />
            ) : (
              <div className="w-full h-64 bg-gray-100 rounded-lg flex items-center justify-center">
                <span className="text-gray-400">Pas de couverture</span>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <h1 className="text-2xl font-bold">{album.title}</h1>

            <div>
              <h2 className="text-sm text-gray-500">Artiste</h2>
              <p className="font-medium">{artistName}</p>
            </div>

            {album.year && (
              <div>
                <h2 className="text-sm text-gray-500">Année</h2>
                <p className="font-medium">{album.year}</p>
              </div>
            )}

            {album.trackCount && (
              <div>
                <h2 className="text-sm text-gray-500">Nombre de titres</h2>
                <p className="font-medium">{album.trackCount}</p>
              </div>
            )}

            {album.duration_seconds && (
              <div>
                <h2 className="text-sm text-gray-500">Durée totale</h2>
                <p className="font-medium">{formatDuration(album.duration_seconds)}</p>
              </div>
            )}

            <div className="flex gap-2 mt-4">
              {artistId && (
                <button
                  onClick={() => navigate(`/artists/${artistId}`)}
                  className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors"
                >
                  Voir l'artiste
                </button>
              )}

              <button
                onClick={handleDownloadAlbum}
                disabled={enqueuing}
                className="px-4 py-2 bg-green-500 text-white rounded-md hover:bg-green-600 transition-colors disabled:opacity-60"
              >
                {enqueuing ? "En cours..." : "Télécharger l'album"}
              </button>
            </div>

            {enqueueResult && <div className="mt-3 text-sm text-gray-700">{enqueueResult}</div>}
          </div>
        </div>

        {/* Section droite - Liste des pistes */}
        <div className="w-full md:w-2/3 bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-bold mb-4">Titres</h2>

          {tracks.length > 0 ? (
            <div className="space-y-2">
              {tracks.map((track: any, index: number) => (
                <div
                  key={track.id || index}
                  className="flex items-center p-2 hover:bg-gray-50 rounded-md"
                >
                  <div className="w-10 text-right pr-4 text-gray-500">
                    {index + 1}
                  </div>
                  <div className="flex-1">
                    <div className="font-medium">{track.title}</div>
                    <div className="text-xs text-gray-500">
                      {track.artists?.map((a: any) => a.name).join(", ") || artistName}
                    </div>
                  </div>
                  {track.duration_seconds && (
                    <div className="text-sm text-gray-500">
                      {formatDuration(track.duration_seconds)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500">Aucune piste trouvée pour cet album.</p>
          )}
        </div>
      </div>
    </div>
  );
}