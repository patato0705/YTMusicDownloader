// src/pages/Home.tsx
import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';

export default function Home(): JSX.Element {
  const { user } = useAuth();
  const { t } = useI18n();

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

      {/* Recent activity placeholder */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
          <CardDescription>Your latest downloads and follows</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            <div className="text-5xl mb-4">🎵</div>
            <p>No recent activity yet</p>
            <p className="text-sm mt-2">Start by browsing and following artists!</p>
          </div>
        </CardContent>
      </Card>

      {/* Stats placeholder */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader>
            <CardDescription>Followed Artists</CardDescription>
            <CardTitle className="text-3xl">0</CardTitle>
          </CardHeader>
        </Card>
        
        <Card>
          <CardHeader>
            <CardDescription>Followed Albums</CardDescription>
            <CardTitle className="text-3xl">0</CardTitle>
          </CardHeader>
        </Card>
        
        <Card>
          <CardHeader>
            <CardDescription>Downloaded Tracks</CardDescription>
            <CardTitle className="text-3xl">0</CardTitle>
          </CardHeader>
        </Card>
        
        <Card>
          <CardHeader>
            <CardDescription>Disk Usage</CardDescription>
            <CardTitle className="text-3xl">0 GB</CardTitle>
          </CardHeader>
        </Card>
      </div>
    </div>
  );
}