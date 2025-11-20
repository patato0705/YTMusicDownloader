// frontend/src/pages/Artist.tsx
import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getArtist } from "../lib/api";
import MediaCard from "../components/MediaCard";
import { formatAlbum } from "../lib/mediaHelpers";

export default function ArtistPage() {
  const { artistId } = useParams<{ artistId: string }>();
  const [artistData, setArtistData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!artistId) return;
    (async () => {
      try {
        const data = await getArtist(artistId);
        setArtistData(data);
      } catch (e: any) {
        setError(e.message || "Erreur lors de la récupération de l'artiste");
      } finally {
        setLoading(false);
      }
    })();
  }, [artistId]);

  const onSelectAlbum = (id: string) => {
    navigate(`/albums/${id}`);
  };
  
  if (loading) return <div className="text-center py-8">Chargement…</div>;
  if (error) return <div className="text-center py-8 text-red-500">Erreur : {error}</div>;
  if (!artistData) return <div className="text-center py-8">Artiste introuvable</div>;

  const artist = artistData.artist;
  const albums = artistData.albums || [];
  const singles = artistData.singles || [];

  return (
    <div className="p-4 md:p-8">
      {/* Header de l'artiste */}
      <div className="flex flex-col md:flex-row items-center md:items-start gap-6 mb-8">
        <div className="w-48 h-48 md:w-64 md:h-64 bg-gray-100 rounded-lg shadow-md overflow-hidden flex-shrink-0">
          {artist.thumbnail ? (
            <img
              src={artist.thumbnail}
              alt={artist.name}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-400">
              Pas d'image
            </div>
          )}
        </div>
        <div>
          <h1 className="text-3xl font-bold mb-2">{artist.name}</h1>
          <p className="text-gray-600 text-lg">
            Découvrez les albums et singles de {artist.name}.
          </p>
        </div>
      </div>

      {/* Section Albums */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Albums</h2>
        {albums.length > 0 ? (
          <div className="flex overflow-x-auto pb-4 gap-4">
            {albums.map((album: any) => {
              const formatted = formatAlbum(album);
              return (
                <MediaCard
                  key={formatted.id}
                  {...formatted}
                  onClick={() => onSelectAlbum(formatted.id)}
                />
              );
            })}
          </div>
        ) : (
          <p className="text-gray-500">Aucun album trouvé pour cet artiste.</p>
        )}
      </section>

      {/* Section Singles */}
      <section>
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Singles et EP</h2>
        {singles.length > 0 ? (
          <div className="flex overflow-x-auto pb-4 gap-4">
            {singles.map((single: any) => {
              const formatted = formatAlbum(single);
              return (
                <MediaCard
                  key={formatted.id}
                  {...formatted}
                  onClick={() => onSelectAlbum(formatted.id)}
                />
              );
            })}
          </div>
        ) : (
          <p className="text-gray-500">Aucun single trouvé pour cet artiste.</p>
        )}
      </section>
    </div>
  );
}