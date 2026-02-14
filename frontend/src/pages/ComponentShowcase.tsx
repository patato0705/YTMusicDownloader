// src/pages/ComponentShowcase.tsx
// This is a demo page to showcase all components - useful for testing and design review
import React, { useState } from 'react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';
import { StatCard } from '../components/ui/StatCard';
import { ActionCard } from '../components/ui/ActionCard';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHero } from '../components/ui/PageHero';
import { Spinner } from '../components/ui/Spinner';
import MediaCard from '../components/MediaCard';
import SearchBar from '../components/SearchBar';

export default function ComponentShowcase(): JSX.Element {
  const [loading, setLoading] = useState(false);
  const [shouldError, setShouldError] = useState(false);

  // This will trigger ErrorBoundary on next render
  if (shouldError) {
    throw new Error('This is a test error from ComponentShowcase!');
  }

  const triggerError = () => {
    setShouldError(true);
  };

  return (
    <div className="relative min-h-screen">
      {/* Background effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
      
      {/* Main content */}
      <div className="relative z-10 space-y-12 pb-12">
        
        {/* Page Title */}
        <PageHero
          badge={{ text: 'Design System', online: true }}
          title={
            <>
              <span className="text-foreground">Component </span>
              <span className="text-gradient">Showcase</span>
            </>
          }
          subtitle="Preview and test all UI components in the design system"
        />

        {/* Buttons Section */}
        <section>
          <SectionHeader>Buttons</SectionHeader>
          <div className="glass rounded-2xl p-8 border-gradient">
            <div className="space-y-4">
              <div className="flex flex-wrap gap-4">
                <Button variant="primary">Primary Button</Button>
                <Button variant="secondary">Secondary Button</Button>
                <Button variant="outline">Outline Button</Button>
                <Button variant="ghost">Ghost Button</Button>
                <Button variant="danger">Danger Button</Button>
              </div>
              <div className="flex flex-wrap gap-4">
                <Button variant="primary" size="sm">Small</Button>
                <Button variant="primary" size="md">Medium</Button>
                <Button variant="primary" size="lg">Large</Button>
              </div>
              <div className="flex flex-wrap gap-4">
                <Button variant="primary" isLoading>Loading...</Button>
                <Button variant="primary" disabled>Disabled</Button>
              </div>
            </div>
          </div>
        </section>

        {/* Cards Section */}
        <section>
          <SectionHeader>Cards</SectionHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card variant="glass">
              <CardHeader>
                <CardTitle>Glassmorphic Card</CardTitle>
                <CardDescription>This card uses the glass effect with backdrop blur</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  Content goes here. The glass effect creates a modern, translucent appearance.
                </p>
              </CardContent>
            </Card>

            <Card variant="default">
              <CardHeader>
                <CardTitle>Default Card</CardTitle>
                <CardDescription>This is a solid card variant</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  This variant provides a solid background for when glass effects aren't needed.
                </p>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* Stat Cards */}
        <section>
          <SectionHeader>Stat Cards</SectionHeader>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              icon={<span className="text-2xl">🎤</span>}
              label="Artists"
              value="1,234"
              trend="+12%"
            />
            <StatCard
              icon={<span className="text-2xl">💿</span>}
              label="Albums"
              value="5,678"
              trend="+8%"
            />
            <StatCard
              icon={<span className="text-2xl">🎵</span>}
              label="Tracks"
              value="45.2K"
              trend="+24%"
            />
            <StatCard
              icon={<span className="text-2xl">⬇️</span>}
              label="Storage"
              value="128 GB"
              trend="+5.2 GB"
            />
          </div>
        </section>

        {/* Action Cards */}
        <section>
          <SectionHeader>Action Cards</SectionHeader>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <ActionCard
              to="#"
              icon={<span className="text-2xl">🔍</span>}
              title="Browse"
              description="Search for new music and discover artists"
            />
            <ActionCard
              to="#"
              icon={<span className="text-2xl">📚</span>}
              title="Library"
              description="Manage your collection of music"
            />
            <ActionCard
              to="#"
              icon={<span className="text-2xl">⚙️</span>}
              title="Settings"
              description="Configure your preferences"
            />
          </div>
        </section>

        {/* Media Cards */}
        <section>
          <SectionHeader>Media Cards</SectionHeader>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
            <MediaCard
              id="1"
              title="The Beatles"
              type="artist"
              thumbnail="https://via.placeholder.com/300"
            />
            <MediaCard
              id="2"
              title="Abbey Road"
              subtitle="The Beatles"
              type="album"
              year="1969"
              thumbnail="https://via.placeholder.com/300"
            />
            <MediaCard
              id="3"
              title="Come Together"
              subtitle="The Beatles"
              type="track"
              thumbnail="https://via.placeholder.com/300"
            />
            <MediaCard
              id="4"
              title="Artist Without Image"
              type="artist"
            />
            <MediaCard
              id="5"
              title="Album Without Image"
              subtitle="Unknown Artist"
              type="album"
            />
          </div>
        </section>

        {/* Search Bar */}
        <section>
          <SectionHeader>Search Bar</SectionHeader>
          <div className="glass rounded-2xl p-8 border-gradient">
            <SearchBar placeholder="Try searching for music..." />
          </div>
        </section>

        {/* Spinners */}
        <section>
          <SectionHeader>Loading Spinners</SectionHeader>
          <div className="glass rounded-2xl p-8 border-gradient">
            <div className="flex items-center gap-8">
              <div className="text-center">
                <Spinner size="sm" className="text-blue-600 dark:text-red-500 mb-2" />
                <p className="text-xs text-muted-foreground">Small</p>
              </div>
              <div className="text-center">
                <Spinner size="md" className="text-blue-600 dark:text-red-500 mb-2" />
                <p className="text-xs text-muted-foreground">Medium</p>
              </div>
              <div className="text-center">
                <Spinner size="lg" className="text-blue-600 dark:text-red-500 mb-2" />
                <p className="text-xs text-muted-foreground">Large</p>
              </div>
            </div>
          </div>
        </section>

        {/* Error Boundary Test */}
        <section>
          <SectionHeader>Error Handling</SectionHeader>
          <div className="glass rounded-2xl p-8 border-gradient">
            <p className="text-muted-foreground mb-4">
              Click this button to trigger an error and see the ErrorBoundary component in action:
            </p>
            <Button variant="danger" onClick={() => setShouldError(true)}>
              Trigger Error
            </Button>
          </div>
        </section>

        {/* Typography */}
        <section>
          <SectionHeader>Typography</SectionHeader>
          <div className="glass rounded-2xl p-8 border-gradient space-y-4">
            <h1 className="text-4xl font-bold text-foreground">Heading 1</h1>
            <h2 className="text-3xl font-bold text-foreground">Heading 2</h2>
            <h3 className="text-2xl font-bold text-foreground">Heading 3</h3>
            <p className="text-foreground">Regular paragraph text with normal weight.</p>
            <p className="text-muted-foreground">Muted text for secondary information.</p>
            <p className="text-gradient text-2xl font-bold">Gradient text effect</p>
          </div>
        </section>

        {/* Colors */}
        <section>
          <SectionHeader>Theme Colors</SectionHeader>
          <div className="glass rounded-2xl p-8 border-gradient">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="space-y-2">
                <div className="h-20 bg-blue-600 dark:bg-red-600 rounded-lg" />
                <p className="text-sm font-medium">Primary</p>
              </div>
              <div className="space-y-2">
                <div className="h-20 bg-slate-200 dark:bg-zinc-800 rounded-lg" />
                <p className="text-sm font-medium">Secondary</p>
              </div>
              <div className="space-y-2">
                <div className="h-20 bg-slate-100 dark:bg-white/10 rounded-lg border border-slate-200 dark:border-white/10" />
                <p className="text-sm font-medium">Glass</p>
              </div>
              <div className="space-y-2">
                <div className="h-20 bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-red-700 dark:to-red-600 rounded-lg" />
                <p className="text-sm font-medium">Gradient</p>
              </div>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}