// src/components/onboarding/slides.tsx
/**
 * The welcome tour's slides: what each role can do, the easily missed parts
 * first. Each slide shows a small live copy of the UI it talks about, built
 * from the app's own components, so it can be recognised later.
 */
import React, { useState } from 'react';
import { ROLES } from '../../api/auth';
import type { Role } from '../../api/auth';
import type { Features } from '../../api/features';
import { SUPPORTED_LOCALES } from '../../config/i18n';
import { useI18n } from '../../contexts/I18nContext';
import { AccentSwatches, ThemeSwitch } from '../layout/AppearanceMenu';
import { JobsBadge, RateLimitBadge } from '../layout/StatusBadges';
import { ActionCard } from '../ui/ActionCard';
import { Artwork } from '../ui/Artwork';
import { Button } from '../ui/Button';
import { Icon } from '../ui/icons';
import type { IconName } from '../ui/icons';
import { HeartIcon } from '../ui/LikeButton';
import { LyricsBadge } from '../ui/LyricsBadge';

export interface Slide {
  id: string;
  /** Lowest role it's shown to */
  minRole: Role;
  /** Only while this feature is switched on */
  feature?: keyof Features;
  /** Translation keys of its text, for this role */
  title: string;
  body: (role: Role) => string;
  /**
   * The live copy of the UI. Its controls answer like the real ones, but
   * change nothing. `controls` ones (real settings, links) go under the text.
   */
  visual: React.FC<VisualProps>;
  controls?: boolean;
}

interface VisualProps {
  role: Role;
  /** Closes the tour (the way out of the last slide's links) */
  close: () => void;
}

export const atLeast = (role: Role, min: Role): boolean => ROLES.indexOf(role) >= ROLES.indexOf(min);

// ---------------------------------------------------------------------------
// Pieces of the copies
// ---------------------------------------------------------------------------

/**
 * The area a copy of the UI sits in, like a corner of a page. Decorative:
 * only a picture (the text says it all), so screen readers skip it.
 */
const Stage: React.FC<{ children: React.ReactNode; className?: string; decorative?: boolean }> = ({ children, className = '', decorative = false }) => (
  <div aria-hidden={decorative || undefined} className={`mb-6 rounded-2xl bg-slate-100/80 dark:bg-white/[0.04] border border-slate-200/70 dark:border-white/10 px-4 py-5 sm:px-6 ${className}`}>
    {children}
  </div>
);

/** A pulsing outline drawing the eye to the part of the copy the slide is about */
const Spotlight: React.FC<{ children: React.ReactNode; rounded?: string; active?: boolean }> = ({ children, rounded = 'rounded-2xl', active = true }) => (
  <span className="relative inline-flex shrink-0">
    {active && (
      <span aria-hidden="true" className={`absolute -inset-1.5 ${rounded} border-2 border-accent-500/80 animate-pulse motion-reduce:animate-none pointer-events-none`} />
    )}
    {children}
  </span>
);

/** A name, as a grey bar: the copies are about where things are, not what's in them */
const TextBar: React.FC<{ className?: string }> = ({ className = 'w-20' }) => (
  <span aria-hidden="true" className={`block h-2.5 rounded-full bg-slate-300/80 dark:bg-white/15 ${className}`} />
);

const FieldLabel: React.FC<{ children: React.ReactNode; id?: string }> = ({ children, id }) => (
  <div id={id} className="mb-2 text-xs font-medium text-muted-foreground">{children}</div>
);

// ---------------------------------------------------------------------------
// The copies
// ---------------------------------------------------------------------------

/** The real language, theme and accent settings: the rest of the tour reads better in the right language */
const Preferences: React.FC = () => {
  const { locale, setLocale, t } = useI18n();

  return (
    <div className="mt-5 space-y-4">
      <div role="group" aria-labelledby="onboarding-language">
        <FieldLabel id="onboarding-language">{t('onboarding.welcome.language')}</FieldLabel>
        {/* Laid out like the theme switch under it */}
        <div className="grid grid-cols-2 gap-1 p-1 rounded-xl bg-slate-100 dark:bg-white/10">
          {SUPPORTED_LOCALES.map((language) => (
            <button
              key={language.code}
              type="button"
              lang={language.code}
              onClick={() => setLocale(language.code)}
              aria-pressed={locale === language.code}
              className={`flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                locale === language.code
                  ? 'bg-white dark:bg-white/15 text-foreground shadow-sm'
                  : 'text-slate-600 dark:text-zinc-400 hover:text-foreground'
              }`}
            >
              <span aria-hidden="true">{language.flag}</span>
              {language.name}
            </button>
          ))}
        </div>
      </div>
      <div>
        <FieldLabel>{t('onboarding.welcome.theme')}</FieldLabel>
        <ThemeSwitch />
      </div>
      <div>
        <FieldLabel>{t('settings.accent.label')}</FieldLabel>
        <AccentSwatches className="px-1" />
      </div>
      <p className="text-xs text-muted-foreground">{t('onboarding.welcome.note')}</p>
    </div>
  );
};

/**
 * An artist's Follow and an album's Download Album, switching the way they do
 * on their pages: Unfollow once followed, In Library once downloaded (for
 * good: an album isn't taken out of the library from there either).
 */
const FollowVisual: React.FC = () => {
  const { t } = useI18n();
  const [followed, setFollowed] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [tried, setTried] = useState({ follow: false, download: false });
  return (
    <Stage className="space-y-4">
      <div className="flex items-center gap-3">
        <Artwork kind="artist" className="w-11 h-11 shrink-0 rounded-full" />
        <TextBar className="flex-1 max-w-[6rem]" />
        <span className="flex-1" />
        <Spotlight rounded="rounded-[1.1rem]" active={!tried.follow}>
          <Button
            size="sm"
            variant={followed ? 'secondary' : 'primary'}
            onClick={() => {
              setFollowed((value) => !value);
              setTried((value) => ({ ...value, follow: true }));
            }}
            className="whitespace-nowrap"
          >
            <Icon name={followed ? 'check' : 'plus'} strokeWidth={2.5} className="w-4 h-4 mr-1.5" />
            {followed ? t('artist.unfollow') : t('artist.follow')}
          </Button>
        </Spotlight>
      </div>
      <div className="flex items-center gap-3">
        <Artwork kind="album" className="w-11 h-11 shrink-0 rounded-lg" />
        <TextBar className="flex-1 max-w-[5rem]" />
        <span className="flex-1" />
        <Spotlight rounded="rounded-[1.1rem]" active={!tried.download}>
          <Button
            size="sm"
            variant={downloaded ? 'secondary' : 'primary'}
            disabled={downloaded}
            onClick={() => {
              setDownloaded(true);
              setTried((value) => ({ ...value, download: true }));
            }}
            className="whitespace-nowrap"
          >
            <Icon name={downloaded ? 'check' : 'download'} strokeWidth={downloaded ? 2.5 : 2} className="w-4 h-4 mr-1.5" />
            {downloaded ? t('album.following') : t('album.download')}
          </Button>
        </Spotlight>
      </div>
    </Stage>
  );
};

/** The right end of the navbar, with its real badges and sample figures: hover or tap them */
const ActivityVisual: React.FC = () => {
  // Ten minutes from when the slide was built, like a fresh pause
  const [pausedUntil] = useState(() => new Date(Date.now() + 10 * 60_000).toISOString());
  return (
    <Stage className="flex justify-center">
      <div className="glass-chrome rounded-2xl shadow-lg flex items-center gap-2.5 h-14 px-4">
        <Spotlight rounded="rounded-2xl">
          <RateLimitBadge until={pausedUntil} gap={10} />
        </Spotlight>
        <Spotlight rounded="rounded-2xl">
          <JobsBadge count={12} byType={{ download_track: 9, download_lyrics: 3 }} gap={10} />
        </Spotlight>
        <span aria-hidden="true" className="ml-2 w-8 h-8 rounded-full bg-gradient-to-br from-accent-500 to-accent-600 shadow-lg" />
      </div>
    </Stage>
  );
};

const LYRICS_KINDS = ['synced', 'plain', 'instrumental', 'pending', 'none'] as const;

/** The lyrics column's badges, as on an album page, and what each one means */
const LyricsVisual: React.FC = () => {
  const { t } = useI18n();
  return (
    <Stage>
      <ul className="space-y-2.5">
        {LYRICS_KINDS.map((kind) => (
          <li key={kind} className="flex items-center gap-3 text-sm">
            <span className="w-9 flex justify-center shrink-0">
              {kind === 'none' || kind === 'pending'
                ? <LyricsBadge iconOnly kind={undefined} pending={kind === 'pending'} />
                : <LyricsBadge iconOnly kind={kind} />}
            </span>
            <span className="min-w-0">
              <span className="font-medium text-foreground">{t(`lyrics.kind.${kind}`)}</span>
              <span className="text-muted-foreground">: {t(`onboarding.lyrics.kinds.${kind}`)}</span>
            </span>
          </li>
        ))}
      </ul>
    </Stage>
  );
};

/** A heart to try, and the recommendation it brings */
const LikesVisual: React.FC = () => {
  const { t } = useI18n();
  const [liked, setLiked] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  return (
    <Stage>
      <div className="flex items-center gap-3">
        <Artwork kind="artist" className="w-11 h-11 shrink-0 rounded-full" />
        <TextBar className="flex-1 max-w-[6rem]" />
        <span className="flex-1" />
        <Spotlight rounded="rounded-full" active={!liked}>
          <button
            type="button"
            onClick={() => setLiked((value) => !value)}
            aria-pressed={liked}
            aria-label={t('onboarding.likes.try')}
            title={t('onboarding.likes.try')}
            className="w-10 h-10 flex items-center justify-center rounded-full border border-slate-200 dark:border-white/10 text-muted-foreground hover:text-foreground hover:bg-slate-200/70 dark:hover:bg-white/10 outline-none focus-visible:ring-2 focus-visible:ring-accent-500/70 transition-colors"
          >
            <HeartIcon filled={liked} className={`w-5 h-5 ${liked ? 'text-rose-500' : ''}`} />
          </button>
        </Spotlight>
      </div>

      <div className="flex justify-center py-2 text-muted-foreground" aria-hidden="true">
        <Icon name="chevronDown" className="w-4 h-4" />
      </div>

      {/* Faint (and out of reach) until the heart is pressed: the recommendation comes from it */}
      <div
        aria-hidden={!liked || undefined}
        className={`transition-opacity duration-500 ${liked ? 'opacity-100' : 'opacity-35 pointer-events-none'}`}
      >
        {dismissed ? (
          <div className="flex items-center justify-between gap-3 rounded-2xl px-4 h-[4.25rem] border border-dashed border-slate-300 dark:border-white/15 text-sm text-muted-foreground animate-fade-in motion-reduce:animate-none">
            <span className="min-w-0 truncate">{t('onboarding.likes.dismissed')}</span>
            <button
              type="button"
              tabIndex={liked ? undefined : -1}
              onClick={() => setDismissed(false)}
              className="shrink-0 font-medium text-accent-600 dark:text-accent-400 hover:underline underline-offset-4 rounded outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
            >
              {t('browse.recommendations.undo')}
            </button>
          </div>
        ) : (
          <div className="group flex items-center gap-3 rounded-2xl p-2.5 bg-white/70 dark:bg-white/5 border border-slate-200/70 dark:border-white/10">
            <Artwork kind="artist" className="w-11 h-11 shrink-0 rounded-full" />
            <span className="flex-1 min-w-0 space-y-1.5">
              <TextBar className="w-24" />
              <span className="block text-xs text-muted-foreground truncate">{t('browse.recommendations.similarToMany', { count: 3 })}</span>
            </span>
            {/* As on Browse: shown on hover where there's a mouse, always on touch screens */}
            <button
              type="button"
              tabIndex={liked ? undefined : -1}
              onClick={() => setDismissed(true)}
              aria-label={t('browse.recommendations.dismiss')}
              title={t('browse.recommendations.dismiss')}
              className="flex w-7 h-7 items-center justify-center rounded-full text-muted-foreground hover:text-foreground hover:bg-slate-200/70 dark:hover:bg-white/10 transition-all outline-none focus-visible:ring-2 focus-visible:ring-accent-500/70 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100"
            >
              <Icon name="close" strokeWidth={2.5} className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </Stage>
  );
};

/** The Browse search bar, and the playlist button next to it */
const PlaylistsVisual: React.FC = () => {
  const { t } = useI18n();
  return (
    <Stage decorative>
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1 min-w-0 flex items-center gap-3 px-4 py-3 rounded-xl glass text-sm text-muted-foreground">
          <Icon name="search" className="w-5 h-5 shrink-0" />
          <span className="truncate">{t('browse.searchInputPlaceholder')}</span>
        </div>
        <Spotlight rounded="rounded-2xl">
          <span className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl glass text-sm text-foreground font-medium whitespace-nowrap">
            <Icon name="music" className="w-5 h-5 text-accent-600 dark:text-accent-400" />
            {t('playlist.importFromPlaylist')}
          </span>
        </Spotlight>
      </div>
    </Stage>
  );
};

/** The Charts link, over the first places of a chart (hovering them as on the Charts page) */
const ChartsVisual: React.FC = () => {
  const { t } = useI18n();
  return (
    <Stage decorative className="flex flex-col items-center gap-3">
      <Spotlight rounded="rounded-2xl">
        <span className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium bg-accent-600 text-white shadow-lg">
          <Icon name="chart" className="w-4 h-4" />
          {t('nav.charts')}
        </span>
      </Spotlight>
      <div className="flex justify-center gap-1 sm:gap-3">
        {[1, 2, 3, 4].map((rank) => (
          <div
            key={rank}
            title={rank === 2 ? t('charts.followedArtist') : undefined}
            className="group p-2 rounded-xl hover:bg-slate-200/60 dark:hover:bg-white/5 transition-all"
          >
            <div className="relative w-12 h-12">
              <span className="absolute -top-1 -left-1 z-10 w-5 h-5 rounded-full bg-accent-600 flex items-center justify-center shadow-lg border-2 border-white dark:border-zinc-900 text-[9px] font-bold text-white">
                {rank}
              </span>
              {rank === 2 && (
                <span className="absolute -top-1 -right-1 z-10 w-5 h-5 rounded-full bg-green-500 flex items-center justify-center shadow-lg border-2 border-white dark:border-zinc-900">
                  <Icon name="check" strokeWidth={3.5} className="w-3 h-3 text-white" />
                </span>
              )}
              <Artwork
                kind="artist"
                className={`w-full h-full rounded-full border-2 transition-all group-hover:border-accent-500 ${rank === 2 ? 'border-accent-500/70' : 'border-slate-300 dark:border-white/20'}`}
              />
            </div>
          </div>
        ))}
      </div>
    </Stage>
  );
};

type AdminTab = 'users' | 'charts' | 'settings' | 'backup';
const ADMIN_TAB_ICONS: Record<AdminTab, IconName> = { users: 'users', charts: 'chart', settings: 'cog', backup: 'database' };

/**
 * The admin panel's tabs, to click through, each saying what it holds.
 * Drawn like FilterTabs on a phone (icon over label) at every width: its
 * wider desktop look follows the screen's width, not the dialog's.
 */
const AdminVisual: React.FC<{ chartsEnabled: boolean }> = ({ chartsEnabled }) => {
  const { t } = useI18n();
  const [active, setActive] = useState<AdminTab>('users');
  const ids: AdminTab[] = chartsEnabled ? ['users', 'charts', 'settings', 'backup'] : ['users', 'settings', 'backup'];
  return (
    <Stage>
      <div role="group" aria-label={t('nav.admin')} className="flex items-center gap-1 glass rounded-2xl p-2">
        {ids.map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => setActive(id)}
            aria-pressed={id === active}
            className={`flex-1 min-w-0 flex flex-col items-center justify-center gap-0.5 px-2 py-2 rounded-xl text-xs font-medium transition-all duration-300 outline-none focus-visible:ring-2 focus-visible:ring-accent-500 ${
              id === active
                ? 'bg-accent-600 text-white shadow-lg'
                : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
            }`}
          >
            <Icon name={ADMIN_TAB_ICONS[id]} className="w-4 h-4 shrink-0" />
            <span className="max-w-full truncate">{t(`admin.tabs.${id}`)}</span>
          </button>
        ))}
      </div>
      <p key={active} aria-live="polite" className="mt-4 text-sm text-center text-muted-foreground animate-fade-in motion-reduce:animate-none">
        {t(`onboarding.admin.tabs.${active}`)}
      </p>
    </Stage>
  );
};

/** The way out: the places to start from, as on the Home page. Following one ends the tour. */
const DoneVisual: React.FC<VisualProps & { chartsEnabled: boolean }> = ({ role, close, chartsEnabled }) => {
  const { t } = useI18n();
  const cards: { to: string; icon: IconName; title: string; description: string }[] = [
    { to: '/browse', icon: 'search', title: t('nav.browse'), description: t('onboarding.done.browse') },
    { to: '/library', icon: 'library', title: t('nav.library'), description: t('onboarding.done.library') },
    ...(editor(role) ? [{ to: '/playlist-import', icon: 'link' as const, title: t('playlist.title'), description: t('onboarding.done.playlist') }] : []),
    ...(chartsEnabled ? [{ to: '/charts', icon: 'chart' as const, title: t('nav.charts'), description: t('onboarding.done.charts') }] : []),
    ...(role === 'administrator' ? [{ to: '/admin', icon: 'cog' as const, title: t('nav.admin'), description: t('onboarding.done.admin') }] : []),
  ];
  return (
    <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
      {cards.map((card, i) => (
        <ActionCard
          key={card.to}
          {...card}
          onClick={close}
          // An odd one out takes the whole last row rather than leave a hole
          className={`!p-4 ${i === cards.length - 1 && cards.length % 2 ? 'sm:col-span-2' : ''}`}
        />
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// The tour
// ---------------------------------------------------------------------------

const editor = (role: Role) => atLeast(role, 'member');

/** Every slide, in order; slidesFor picks those of a role */
function allSlides(features: Features): Slide[] {
  return [
    {
      id: 'welcome',
      minRole: 'visitor',
      title: 'onboarding.welcome.title',
      body: (role) => (editor(role) ? 'onboarding.welcome.body' : 'onboarding.welcome.bodyVisitor'),
      visual: Preferences,
      controls: true,
    },
    {
      id: 'follow',
      minRole: 'member',
      title: 'onboarding.follow.title',
      body: () => 'onboarding.follow.body',
      visual: FollowVisual,
    },
    {
      id: 'activity',
      minRole: 'member',
      title: 'onboarding.activity.title',
      body: () => 'onboarding.activity.body',
      visual: ActivityVisual,
    },
    {
      id: 'lyrics',
      minRole: 'visitor',
      title: 'onboarding.lyrics.title',
      body: (role) => (editor(role) ? 'onboarding.lyrics.bodyEditor' : 'onboarding.lyrics.body'),
      visual: LyricsVisual,
    },
    {
      id: 'likes',
      minRole: 'member',
      title: 'onboarding.likes.title',
      body: () => 'onboarding.likes.body',
      visual: LikesVisual,
    },
    {
      id: 'playlists',
      minRole: 'member',
      title: 'onboarding.playlists.title',
      body: () => 'onboarding.playlists.body',
      visual: PlaylistsVisual,
    },
    {
      id: 'charts',
      minRole: 'visitor',
      feature: 'charts_enabled',
      title: 'onboarding.charts.title',
      body: (role) => (role === 'administrator' ? 'onboarding.charts.bodyAdmin' : 'onboarding.charts.body'),
      visual: ChartsVisual,
    },
    {
      id: 'admin',
      minRole: 'administrator',
      title: 'onboarding.admin.title',
      body: () => 'onboarding.admin.body',
      visual: () => <AdminVisual chartsEnabled={features.charts_enabled} />,
    },
    {
      id: 'done',
      minRole: 'visitor',
      title: 'onboarding.done.title',
      body: () => 'onboarding.done.body',
      visual: (props) => <DoneVisual {...props} chartsEnabled={features.charts_enabled} />,
      controls: true,
    },
  ];
}

/** The slides a role gets, leaving out features that are switched off */
export function slidesFor(role: Role, features: Features): Slide[] {
  return allSlides(features).filter((slide) => atLeast(role, slide.minRole) && (!slide.feature || features[slide.feature]));
}
