// src/pages/Home.tsx
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';
import { getLibraryStats, getLibraryAlbums } from '../api/library';
import { Spinner } from '../components/ui/Spinner';
import { formatNumber } from '../utils';

export default function Home(): JSX.Element {
  const { user } = useAuth();
  const { t } = useI18n();
  const [stats, setStats] = useState<any>(null);
  const [recentAlbums, setRecentAlbums] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHomeData();
  }, []);

  const loadHomeData = async () => {
    setLoading(true);
    try {
      const [statsData, albumsData] = await Promise.all([
        getLibraryStats(),
        getLibraryAlbums({ limit: 5, sort_by: 'followed_at', order: 'desc' }),
      ]);
      setStats(statsData);
      setRecentAlbums(albumsData?.albums || []);
    } catch (err) {
      console.error('Failed to load home data:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Welcome section */}
      <div>
        <h1 className="text-4xl font-bold text-foreground mb-2">
          {t('common.search')} {user?.username}! 👋
        </h1>
        <p className="text-lg text-muted-foreground">
          Welcome to your music library
        </p>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Card className="hover:border-primary transition-colors cursor-pointer">
          <Link to="/browse">
            <CardHeader>
              <div className="text-4xl mb-2">🔍</div>
              <CardTitle>{t('nav.browse')}</CardTitle>
              <CardDescription>
                Search for artists, albums, and tracks
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>

        <Card className="hover:border-primary transition-colors cursor-pointer">
          <Link to="/library">
            <CardHeader>
              <div className="text-4xl mb-2">📚</div>
              <CardTitle>{t('nav.library')}</CardTitle>
              <CardDescription>
                View your followed artists and albums
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>

        <Card className="hover:border-primary transition-colors cursor-pointer">
          <Link to="/settings">
            <CardHeader>
              <div className="text-4xl mb-2">⚙️</div>
              <CardTitle>{t('nav.settings')}</CardTitle>
              <CardDescription>
                Manage your account and preferences
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>
      </div>

      {/* Recent activity */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
          <CardDescription>Your latest downloads and follows</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Spinner className="text-primary" />
            </div>
          ) : recentAlbums.length > 0 ? (
            <div className="space-y-3">
              {recentAlbums.map((album) => (
                <Link
                  key={album.id}
                  to={`/albums/${encodeURIComponent(album.id)}`}
                  className="flex items-center gap-4 p-3 rounded-lg hover:bg-accent transition-colors"
                >
                  {album.thumbnail && (
                    <img
                      src={album.thumbnail}
                      alt={album.title}
                      className="w-12 h-12 rounded object-cover"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-foreground truncate">{album.title}</p>
                    <p className="text-sm text-muted-foreground truncate">{album.artist?.name}</p>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {album.tracks_downloaded}/{album.tracks_total} tracks
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <div className="text-5xl mb-4">🎵</div>
              <p>No recent activity yet</p>
              <p className="text-sm mt-2">Start by browsing and following artists!</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader>
            <CardDescription>Followed Artists</CardDescription>
            <CardTitle className="text-3xl">
              {loading ? <Spinner size="sm" /> : formatNumber(stats?.artists?.total || 0)}
            </CardTitle>
          </CardHeader>
        </Card>
        
        <Card>
          <CardHeader>
            <CardDescription>Followed Albums</CardDescription>
            <CardTitle className="text-3xl">
              {loading ? <Spinner size="sm" /> : formatNumber(stats?.albums?.total || 0)}
            </CardTitle>
          </CardHeader>
        </Card>
        
        <Card>
          <CardHeader>
            <CardDescription>Downloaded Tracks</CardDescription>
            <CardTitle className="text-3xl">
              {loading ? <Spinner size="sm" /> : formatNumber(stats?.tracks?.downloaded || 0)}
            </CardTitle>
          </CardHeader>
        </Card>
        
        <Card>
          <CardHeader>
            <CardDescription>Disk Usage</CardDescription>
            <CardTitle className="text-3xl">
              {loading ? <Spinner size="sm" /> : `${stats?.storage?.estimated_gb?.toFixed(2) || 0} GB`}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>
    </div>
  );
}