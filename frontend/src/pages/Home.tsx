// src/pages/Home.tsx
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';
import { StatCard } from '../components/ui/StatCard';
import { ActionCard } from '../components/ui/ActionCard';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHero } from '../components/ui/PageHero';
import { getLibraryStats, getLibraryAlbums } from '../api/library';
import { getImageUrl } from '../api/media';
import { Spinner } from '../components/ui/Spinner';
import { formatNumber } from '../utils';

// Icon components (using Unicode until we potentially add a proper icon library)
const MusicIcon = () => <span className="text-2xl">🎵</span>;
const SearchIcon = () => <span className="text-2xl">🔍</span>;
const LibraryIcon = () => <span className="text-2xl">📚</span>;
const SettingsIcon = () => <span className="text-2xl">⚙️</span>;
const DownloadIcon = () => <span className="text-2xl">⬇️</span>;
const ActivityIcon = () => <span className="text-2xl">⚡</span>;

export default function Home(): JSX.Element {
  const { user } = useAuth();
  const { t } = useI18n();
  const [stats, setStats] = useState<any>(null);
  const [recentAlbums, setRecentAlbums] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [imageErrors, setImageErrors] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadHomeData();
  }, []);

  const loadHomeData = async () => {
    setLoading(true);
    try {
      const [statsData, albumsData] = await Promise.all([
        getLibraryStats(),
        getLibraryAlbums({ limit: 6, sort_by: 'followed_at', order: 'desc' }),
      ]);
      setStats(statsData);
      setRecentAlbums(albumsData?.albums || []);
    } catch (err) {
      console.error('Failed to load home data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleImageError = (albumId: string) => {
    setImageErrors(prev => new Set(prev).add(albumId));
  };

  return (
    <div className="relative min-h-screen">
      {/* Background effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
      
      {/* Main content */}
      <div className="relative z-10 space-y-12 pb-12">
        {/* Hero section */}
        <PageHero
          badge={{ text: 'System Online', online: true }}
          title={
            <>
              <span className="text-foreground">Welcome back, </span>
              <span className="text-gradient">{user?.username}</span>
            </>
          }
          subtitle="Your personal music library management system. Download, organize, and sync with Jellyfin."
        />

        {/* Quick Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            icon={<LibraryIcon />}
            label="Artists"
            value={loading ? <Spinner size="sm" /> : formatNumber(stats?.artists?.total || 0)}
            trend="+12%"
            loading={loading}
          />
          <StatCard
            icon={<MusicIcon />}
            label="Albums"
            value={loading ? <Spinner size="sm" /> : formatNumber(stats?.albums?.total || 0)}
            trend="+8%"
            loading={loading}
          />
          <StatCard
            icon={<DownloadIcon />}
            label="Tracks"
            value={loading ? <Spinner size="sm" /> : formatNumber(stats?.tracks?.downloaded || 0)}
            trend="+24%"
            loading={loading}
          />
          <StatCard
            icon={<ActivityIcon />}
            label="Storage"
            value={loading ? <Spinner size="sm" /> : `${stats?.storage?.estimated_gb?.toFixed(1) || 0} GB`}
            trend="+2.1 GB"
            loading={loading}
          />
        </div>

        {/* Quick Actions */}
        <div>
          <SectionHeader>Quick Actions</SectionHeader>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <ActionCard
              to="/browse"
              icon={<SearchIcon />}
              title={t('nav.browse')}
              description="Search YouTube Music for new content"
              gradient="from-blue-500/10 to-indigo-500/10 dark:from-red-900/20 dark:to-red-800/20"
            />
            
            <ActionCard
              to="/library"
              icon={<LibraryIcon />}
              title={t('nav.library')}
              description="Manage your followed artists and albums"
              gradient="from-indigo-500/10 to-violet-500/10 dark:from-red-900/20 dark:via-purple-900/15 dark:to-red-800/20"
            />
            
            <ActionCard
              to="/settings"
              icon={<SettingsIcon />}
              title={t('nav.settings')}
              description="Configure downloads and preferences"
              gradient="from-violet-500/10 to-blue-500/10 dark:from-red-950/20 dark:to-red-900/20"
            />
          </div>
        </div>

        {/* Recent Activity */}
        <div>
          <SectionHeader>Recent Activity</SectionHeader>
          
          <div className="glass rounded-2xl p-6 border-gradient">
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <div className="text-center">
                  <Spinner className="text-blue-600 dark:text-red-500 mb-4" />
                  <p className="text-muted-foreground">Loading recent activity...</p>
                </div>
              </div>
            ) : recentAlbums.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {recentAlbums.map((album) => {
                  const thumbnailUrl = getImageUrl(album.image_local || album.thumbnail);
                  const showImage = thumbnailUrl && !imageErrors.has(album.id);
                  const progress = album.tracks_total > 0 
                    ? (album.tracks_downloaded / album.tracks_total) * 100 
                    : 0;
                  
                  return (
                    <Link
                      key={album.id}
                      to={`/albums/${encodeURIComponent(album.id)}`}
                      className="group relative overflow-hidden rounded-xl bg-slate-50 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 border border-slate-200 dark:border-white/10 hover:border-blue-400/50 dark:hover:border-red-600/50 transition-all duration-300 hover-lift"
                    >
                      {/* Album art or placeholder */}
                      <div className="relative aspect-square overflow-hidden">
                        {showImage ? (
                          <>
                            <img
                              src={thumbnailUrl}
                              alt={album.title}
                              className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
                              onError={() => handleImageError(album.id)}
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
                          </>
                        ) : (
                          <div className="w-full h-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 flex items-center justify-center">
                            <MusicIcon />
                          </div>
                        )}
                        
                        {/* Progress indicator */}
                        {progress < 100 && (
                          <div className="absolute top-2 right-2 px-2 py-1 rounded-full glass-strong text-xs font-medium text-blue-600 dark:text-red-400">
                            {Math.round(progress)}%
                          </div>
                        )}
                      </div>
                      
                      {/* Album info */}
                      <div className="p-4">
                        <h3 className="font-semibold text-foreground truncate mb-1 group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors">
                          {album.title}
                        </h3>
                        <p className="text-sm text-muted-foreground truncate mb-3">
                          {album.artist?.name}
                        </p>
                        
                        {/* Download progress bar */}
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>{album.tracks_downloaded}/{album.tracks_total} tracks</span>
                            {progress === 100 && (
                              <span className="text-blue-600 dark:text-red-400">✓ Complete</span>
                            )}
                          </div>
                          <div className="h-1 bg-slate-200 dark:bg-white/10 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-red-700 dark:to-red-500 transition-all duration-500"
                              style={{ width: `${progress}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-16">
                <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-4">
                  <MusicIcon />
                </div>
                <h3 className="text-xl font-semibold mb-2">No activity yet</h3>
                <p className="text-muted-foreground mb-6">
                  Start by browsing and following your favorite artists
                </p>
                <Link
                  to="/browse"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-red-700 dark:to-red-600 text-white font-medium hover:shadow-lg hover:shadow-blue-600/50 dark:hover:shadow-red-700/50 transition-all duration-300"
                >
                  <SearchIcon />
                  Browse Music
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}