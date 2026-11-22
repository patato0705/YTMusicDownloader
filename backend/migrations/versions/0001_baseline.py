"""Baseline: the schema when migrations were introduced (V1).

A database created before then is rebuilt with it, its rows copied
over (backend/migrations/runner.py, _adopt).

Created 2026-11-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


# Forward only: going back means restoring the copy taken before the
# upgrade (config/db-backups/) and running the previous image.
def upgrade() -> None:
    op.create_table('artists',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('folder', sa.String(length=255), nullable=True),
    sa.Column('image_local', sa.String(length=1024), nullable=True),
    sa.Column('banner_local', sa.String(length=1024), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('genres', sqlite.JSON(), nullable=True),
    sa.Column('musicbrainz_id', sa.String(length=64), nullable=True),
    sa.Column('deezer_id', sa.String(length=64), nullable=True),
    sa.Column('genres_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_artists'))
    )
    with op.batch_alter_table('artists', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_artists_name'), ['name'], unique=False)

    op.create_table('exclusions',
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('item_id', sa.String(length=64), nullable=False),
    sa.Column('reason', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('artist_id', sa.String(length=64), nullable=True),
    sa.Column('artist_name', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('kind', 'item_id', name=op.f('pk_exclusions'))
    )
    op.create_table('user_channels',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_channels'))
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=64, collation='NOCASE'), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('oidc_issuer', sa.String(length=512), nullable=True),
    sa.Column('oidc_subject', sa.String(length=255), nullable=True),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('must_change_password', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tokens_valid_after', sa.DateTime(timezone=True), nullable=True),
    sa.Column('onboarding_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('oidc_issuer', 'oidc_subject', name=op.f('uq_users_oidc_issuer_oidc_subject')),
    sqlite_autoincrement=True
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_username'), ['username'], unique=True)

    op.create_table('video_songs',
    sa.Column('video_id', sa.String(length=64), nullable=False),
    sa.Column('song_id', sa.String(length=64), nullable=True),
    sa.Column('song_title', sa.String(length=1024), nullable=True),
    sa.Column('album_id', sa.String(length=64), nullable=True),
    sa.Column('album_title', sa.String(length=255), nullable=True),
    sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('video_id', name=op.f('pk_video_songs'))
    )
    op.create_table('albums',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('folder', sa.String(length=255), nullable=True),
    sa.Column('type', sa.String(length=32), nullable=True),
    sa.Column('artist_id', sa.String(length=64), nullable=True),
    sa.Column('playlist_id', sa.String(length=255), nullable=True),
    sa.Column('year', sa.String(length=16), nullable=True),
    sa.Column('image_local', sa.String(length=2048), nullable=True),
    sa.Column('cover_id', sa.String(length=1024), nullable=True),
    sa.Column('on_artist_page', sa.Boolean(), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('genres', sqlite.JSON(), nullable=True),
    sa.Column('genres_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('mode', sa.String(length=32), nullable=False),
    sa.Column('download_status', sa.String(length=32), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], name=op.f('fk_albums_artist_id_artists'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_albums'))
    )
    with op.batch_alter_table('albums', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_albums_artist_id'), ['artist_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_albums_title'), ['title'], unique=False)

    op.create_table('artist_likes',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('artist_id', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], name=op.f('fk_artist_likes_artist_id_artists'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_artist_likes_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'artist_id', name=op.f('pk_artist_likes'))
    )
    with op.batch_alter_table('artist_likes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_artist_likes_artist_id'), ['artist_id'], unique=False)

    op.create_table('artist_subscriptions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('artist_id', sa.String(length=64), nullable=False),
    sa.Column('mode', sa.String(length=32), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('chart_followed', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], name=op.f('fk_artist_subscriptions_artist_id_artists'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_artist_subscriptions'))
    )
    with op.batch_alter_table('artist_subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_artist_subscriptions_artist_id'), ['artist_id'], unique=False)

    op.create_table('chart_subscriptions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('top_n_artists', sa.Integer(), nullable=False),
    sa.Column('keep_weeks', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_chart_subscriptions_created_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chart_subscriptions'))
    )
    with op.batch_alter_table('chart_subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chart_subscriptions_country_code'), ['country_code'], unique=True)

    op.create_table('dismissed_recommendations',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('artist_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('thumbnail', sa.String(length=1024), nullable=True),
    sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_dismissed_recommendations_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'artist_id', name=op.f('pk_dismissed_recommendations'))
    )
    op.create_table('jobs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('type', sa.String(length=64), nullable=False),
    sa.Column('payload', sqlite.JSON(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('result', sqlite.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reserved_by', sa.String(length=128), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_jobs_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_jobs'))
    )
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_jobs_scheduled_at'), ['scheduled_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_type'), ['type'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_user_id'), ['user_id'], unique=False)

    op.create_table('playlists',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('author', sa.String(length=255), nullable=True),
    sa.Column('thumbnail', sa.String(length=1024), nullable=True),
    sa.Column('mode', sa.String(length=16), nullable=False),
    sa.Column('followed', sa.Boolean(), nullable=False),
    sa.Column('m3u', sa.Boolean(), nullable=False),
    sa.Column('m3u_name', sa.String(length=255), nullable=True),
    sa.Column('available_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_playlists_created_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_playlists'))
    )
    op.create_table('refresh_tokens',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('family_id', sa.String(length=32), nullable=False),
    sa.Column('replaced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['replaced_by_id'], ['refresh_tokens.id'], name=op.f('fk_refresh_tokens_replaced_by_id_refresh_tokens'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens'))
    )
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refresh_tokens_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_family_id'), ['family_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_replaced_by_id'), ['replaced_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_user_id'), ['user_id'], unique=False)

    op.create_table('related_artists',
    sa.Column('artist_id', sa.String(length=64), nullable=False),
    sa.Column('related_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('thumbnail', sa.String(length=1024), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], name=op.f('fk_related_artists_artist_id_artists'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('artist_id', 'related_id', name=op.f('pk_related_artists'))
    )
    with op.batch_alter_table('related_artists', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_related_artists_related_id'), ['related_id'], unique=False)

    op.create_table('settings',
    sa.Column('key', sa.String(length=128), nullable=False),
    sa.Column('value', sa.Text(), nullable=True),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_settings_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_settings'))
    )
    op.create_table('chart_sightings',
    sa.Column('country_code', sa.String(length=2), nullable=False),
    sa.Column('artist_id', sa.String(length=64), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['country_code'], ['chart_subscriptions.country_code'], name=op.f('fk_chart_sightings_country_code_chart_subscriptions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('country_code', 'artist_id', name=op.f('pk_chart_sightings'))
    )
    with op.batch_alter_table('chart_sightings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chart_sightings_artist_id'), ['artist_id'], unique=False)

    op.create_table('playlist_entries',
    sa.Column('playlist_id', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('video_id', sa.String(length=64), nullable=True),
    sa.Column('title', sa.String(length=1024), nullable=False),
    sa.Column('artist_id', sa.String(length=64), nullable=True),
    sa.Column('artist_name', sa.String(length=255), nullable=True),
    sa.Column('album_id', sa.String(length=64), nullable=True),
    sa.Column('album_title', sa.String(length=255), nullable=True),
    sa.Column('duration', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['playlist_id'], ['playlists.id'], name=op.f('fk_playlist_entries_playlist_id_playlists'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('playlist_id', 'position', name=op.f('pk_playlist_entries'))
    )
    with op.batch_alter_table('playlist_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_playlist_entries_album_id'), ['album_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_playlist_entries_video_id'), ['video_id'], unique=False)

    op.create_table('tracks',
    sa.Column('id', sa.String(length=128), nullable=False),
    sa.Column('title', sa.String(length=1024), nullable=False),
    sa.Column('duration', sa.Integer(), nullable=True),
    sa.Column('artists', sqlite.JSON(), nullable=True),
    sa.Column('album_id', sa.String(length=64), nullable=True),
    sa.Column('track_number', sa.Integer(), nullable=True),
    sa.Column('lyrics', sa.String(length=16), nullable=True),
    sa.Column('lyrics_local', sa.String(length=1024), nullable=True),
    sa.Column('lyrics_retried_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('file_path', sa.String(length=2048), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=64), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('artist_valid', sa.Boolean(), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['album_id'], ['albums.id'], name=op.f('fk_tracks_album_id_albums'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tracks'))
    )
    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tracks_album_id'), ['album_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tracks_title'), ['title'], unique=False)

