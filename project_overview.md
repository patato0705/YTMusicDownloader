# Music Management Application - Project Overview & Context

## Project Description

A self-hosted music management web application that syncs music from YouTube Music, manages downloads, and provides library organization. Built with FastAPI (Python) backend and React/TypeScript frontend.

---

## Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.11)
- **Database**: SQLite with SQLAlchemy ORM
- **Jobs/Workers**: Custom job queue system with worker threads
- **External API**: ytmusicapi (YouTube Music)
- **Download**: yt-dlp for audio downloads

### Frontend
- **Framework**: React with TypeScript
- **Build**: Vite
- **Routing**: React Router
- **State Management**: Context API / React Query (assumed)

### Architecture Pattern
**Router → Service → Adapter**
- **Routers** (`backend/routers/`): Handle HTTP requests, validation, responses
- **Services** (`backend/services/`): Business logic, database operations, caching
- **Adapters** (`backend/ytm_service/adapter.py`): External API calls, data normalization

---

## Core Database Models

### Content Models
```python
# backend/models.py

class Artist(Base):
    id: str (primary key)
    name: str
    thumbnails: JSON
    image_local: str (file path)
    created_at: datetime
    # REMOVED: followed field (was boolean)

class Album(Base):
    id: str (primary key)
    title: str
    artist_id: str (foreign key)
    thumbnails: JSON
    playlist_id: str
    year: str
    image_local: str

class Track(Base):
    id: str (primary key)
    title: str
    duration: int
    artists: JSON (list of dicts)
    album_id: str (foreign key)
    track_number: int
    has_lyrics: bool
    lyrics_local: str
    file_path: str
    status: str (new/downloading/completed/error)
    artist_valid: bool
    created_at: datetime
```

### Subscription Models (Core Feature)
```python
class ArtistSubscription(Base):
    id: int (primary key)
    artist_id: str (foreign key → artists.id)
    mode: str  # "light" or "full"
    enabled: bool
    created_at: datetime
    last_synced_at: datetime (nullable)
    last_error: str (nullable)

class AlbumSubscription(Base):
    id: int (primary key)
    album_id: str (foreign key → albums.id)
    artist_id: str (foreign key → artists.id, nullable)
    mode: str  # "metadata" or "download"
    created_at: datetime
    last_synced_at: datetime (nullable)
    download_status: str
    last_error: str (nullable)

class ChartSubscription(Base):
    id: int (primary key)
    country_code: str (unique, 2 letters)
    enabled: bool
    top_n_artists: int (1-40)
    created_at: datetime
    created_by: int (foreign key → users.id)
    last_synced_at: datetime (nullable)
    last_error: str (nullable)

class ChartSnapshot(Base):
    id: int (primary key)
    country_code: str
    snapshot_date: datetime
    data: JSON (full chart data)
```

### System Models
```python
class Job(Base):
    id: int (primary key)
    type: str (download_track, import_album, sync_artist, sync_chart)
    payload: JSON
    status: str (queued/running/completed/failed)
    attempts: int
    max_attempts: int
    priority: int
    scheduled_at: datetime
    started_at: datetime
    finished_at: datetime
    last_error: str
    result: JSON
    created_at: datetime
    reserved_by: str
    user_id: int (foreign key)

class User(Base):
    id: int (primary key)
    username: str (unique)
    email: str (unique)
    password_hash: str
    role: str (administrator/member/visitor)
    is_active: bool
    created_at: datetime
    last_login_at: datetime

class RefreshToken(Base):
    id: int (primary key)
    token: str (unique)
    user_id: int (foreign key)
    expires_at: datetime
    created_at: datetime
    revoked: bool

class Setting(Base):
    key: str (primary key)
    value: str
    type: str (int/bool/string/json)
    description: str
    updated_at: datetime
    updated_by: int (foreign key)
```

---

## Key Services

### backend/services/subscriptions.py
Manages subscriptions (artist and album):
- `subscribe_to_artist(session, artist_id, mode)` - mode: "light" or "full"
- `subscribe_to_album(session, album_id, mode)` - mode: "metadata" or "download"
- `update_artist_subscription_mode()` - upgrade/downgrade
- `upgrade_all_album_subscriptions_to_download()` - when upgrading artist
- `downgrade_all_album_subscriptions_to_metadata()` - when downgrading artist
- `get_artist_status()` - returns subscription info

### backend/services/artists.py
Artist CRUD and metadata:
- `upsert_artist()` - create/update artist record
- `fetch_and_upsert_artist()` - fetch from YTMusic and save to DB
- `ensure_artist_banner()` - download and save artist image

### backend/services/albums.py
Album operations (assumed):
- `list_albums_for_artist_from_db()` - get albums for an artist
- `fetch_albums_for_artist()` - fetch from YTMusic

### backend/services/charts.py
Chart operations:
- `fetch_chart()` - get chart from YTMusic
- `sync_chart()` - fetch and identify new artists
- `save_chart_snapshot()` - store historical data
- CRUD for ChartSubscription

### backend/services/auth.py
Authentication:
- `hash_password()`, `verify_password()`
- `create_access_token()`, `verify_access_token()`
- `create_refresh_token()`, `verify_refresh_token()`
- `authenticate_user()`, `create_user()`
- `ensure_first_admin()` - create default admin on startup

### backend/services/admin.py
Admin operations:
- `list_users()`, `update_user_role()`
- `activate_user()`, `deactivate_user()`, `delete_user()`
- `get_user_stats()`

---

## Job System

### Worker (`backend/jobs/worker.py`)
Continuously polls for jobs and executes them.

### Job Queue (`backend/jobs/jobqueue.py`)
- `enqueue_job()` - add job to queue
- Jobs have priority, max_attempts, scheduled_at

### Task Handlers (`backend/jobs/tasks.py`)
```python
# Job types and their handlers:
_TASK_MAP = {
    "download_track": download_track,
    "download_lyrics": download_lyrics,
    "import_album": import_album,
    "sync_artist": sync_artist,
    "sync_chart": sync_chart,
}
```

**sync_artist(session, artist_id)**
- Fetches latest albums for an artist
- Respects subscription mode:
  - Light mode: imports metadata only, no downloads
  - Full mode: imports everything, queues download jobs
- Downloads artist banner
- Creates album subscriptions based on mode

**sync_chart(session, country_code)**
- Fetches chart data from YTMusic
- Identifies new artists to follow
- Creates artist subscriptions (mode="full")
- Queues sync_artist jobs

**import_album(session, browse_id, artist_id)**
- Fetches album details from YTMusic
- Creates/updates Album and Track records
- Queues download_track jobs

**download_track(session, track_id, ...)**
- Downloads audio using yt-dlp
- Updates Track.file_path and Track.status

---

## Routing Structure

### backend/routers/

**auth.py** - Authentication
- POST `/api/auth/register` - Register (admin only)
- POST `/api/auth/login` - Login
- POST `/api/auth/logout` - Logout
- POST `/api/auth/refresh` - Refresh token
- GET `/api/auth/me` - Current user
- POST `/api/auth/change-password` - Change password
- GET `/api/auth/registration-status` - Check if registration enabled

**admin.py** - Admin panel
- GET `/api/admin/users` - List users
- POST `/api/admin/users` - Create user
- PATCH `/api/admin/users/{id}/role` - Update role
- POST `/api/admin/users/{id}/activate` - Activate
- POST `/api/admin/users/{id}/deactivate` - Deactivate
- DELETE `/api/admin/users/{id}` - Delete user
- GET `/api/admin/settings` - List settings
- GET `/api/admin/settings/{key}` - Get setting
- PUT `/api/admin/settings/{key}` - Update setting
- DELETE `/api/admin/settings/{key}` - Delete setting

**artists.py** - Artist management
- GET `/api/artists/{id}` - Get artist (smart fetch based on subscription)
- POST `/api/artists/{id}/follow` - Follow artist (full mode)
- DELETE `/api/artists/{id}/follow` - Unfollow artist
- PATCH `/api/artists/{id}/mode` - Update subscription mode (light/full)

**charts.py** - Charts
- GET `/api/charts/{country_code}` - Get chart
- POST `/api/charts/{country_code}/follow` - Follow chart (admin)
- DELETE `/api/charts/{country_code}/follow` - Unfollow chart (admin)
- PATCH `/api/charts/{country_code}` - Update chart settings (admin)
- GET `/api/charts` - List chart subscriptions (admin)

---

## Current Major Refactoring: Subscription System Redesign

### Problem Being Solved
The old system used `artist.followed` (boolean) to track if an artist was being synced. This was confusing because:
- Following a single album would create an artist record but not sync metadata
- Artist data was incomplete (no image, no other albums visible)
- Couldn't distinguish between "has some data" and "actively syncing"

### New System: Subscription-Based with Modes

**Core Principle**: Subscriptions ≠ Library
- **Subscriptions**: Control what gets synced/downloaded (ephemeral)
- **Library**: Actual files and metadata on disk (persistent)

**Subscription Modes:**

Artist Subscriptions:
- **No subscription**: Artist not in DB (cloud icon ☁️)
- **mode="light"**: Metadata synced, no downloads (disk icon 💾)
- **mode="full"**: Everything downloaded (checkmark ✓)

Album Subscriptions:
- **No subscription**: Album not in DB (cloud icon ☁️)
- **mode="metadata"**: In DB for browsing, not downloading (disk icon 💾)
- **mode="download"**: Actively downloading (checkmark ✓)

### Key Behaviors

**Following a Single Album:**
1. Creates `AlbumSubscription(mode="download")`
2. Auto-creates `ArtistSubscription(mode="light")` if doesn't exist
3. Queues `import_album` job (downloads tracks)
4. Queues `sync_artist` job (fetches all albums metadata + banner)
5. Result: Album downloaded, artist fully browsable, other albums visible but not downloaded

**Following an Artist:**
1. Creates/upgrades `ArtistSubscription(mode="full")`
2. Upgrades all `AlbumSubscription` to `mode="download"`
3. Queues `sync_artist` job
4. Result: Everything downloaded

**Unfollowing an Artist:**
1. Deletes `ArtistSubscription`
2. Downgrades all `AlbumSubscription` to `mode="metadata"`
3. Files remain on disk (not deleted)
4. Result: Stops syncing, keeps files

**Upgrading Artist (Light → Full):**
1. Updates `ArtistSubscription.mode` to "full"
2. Upgrades all `AlbumSubscription` to `mode="download"`
3. Queues `sync_artist` job
4. Result: Downloads all albums

### Files Modified/Created (Current Session)

**Database Models** (`backend/models.py`):
- ✅ Removed `Artist.followed` field
- ✅ Added `ArtistSubscription.mode` field
- ✅ Added `AlbumSubscription.mode` field

**Services**:
- ✅ `backend/services/subscriptions.py` - Complete rewrite with mode support
- ✅ `backend/services/artists.py` - Removed `followed` logic
- ✅ `backend/services/admin.py` - Already created (user management)

**Routers**:
- ✅ `backend/routers/artists.py` - Updated with new subscription logic
- ✅ `backend/routers/admin.py` - Already created (user + settings management)
- ✅ `backend/routers/charts.py` - Already created

**Jobs**:
- ✅ `backend/jobs/tasks.py::sync_artist()` - Updated to respect mode
- ✅ `backend/jobs/tasks.py::sync_chart()` - Updated to create subscriptions

### Still TODO

**Album Following** (`backend/routers/albums.py` - needs creation):
- POST `/api/albums/{id}/follow` - Follow album (creates light artist sub)
- DELETE `/api/albums/{id}/follow` - Unfollow album
- Need to ensure it auto-creates light artist subscription

**Library Management** (new endpoints needed):
- DELETE `/api/library/artists/{id}` - Delete artist from library (files + DB)
- DELETE `/api/library/albums/{id}` - Delete album from library (files + DB)
- POST `/api/library/cleanup` - Remove orphaned data

**Charts Service** (`backend/services/charts.py`):
- Update `sync_chart()` to use new subscription system
- Already mostly done

**Frontend Updates**:
- Update icons based on subscription status
- Add mode upgrade/downgrade buttons
- Show subscription status in UI
- Library management page

---

## File Structure

```
backend/
├── routers/          # API endpoints
│   ├── auth.py
│   ├── admin.py
│   ├── artists.py
│   ├── charts.py
│   └── (albums.py - needs creation)
├── services/         # Business logic
│   ├── auth.py
│   ├── admin.py
│   ├── artists.py
│   ├── albums.py
│   ├── charts.py
│   ├── subscriptions.py
│   └── tracks.py
├── jobs/             # Background jobs
│   ├── worker.py
│   ├── jobqueue.py
│   └── tasks.py
├── schemas/          # Pydantic models
│   ├── auth.py
│   ├── charts.py
│   ├── common.py
│   ├── jobs.py
│   ├── settings.py
│   └── ytmusic.py
├── ytm_service/      # YouTube Music adapter
│   ├── adapter.py
│   └── normalizers.py
├── models.py         # SQLAlchemy ORM models
├── dependencies.py   # FastAPI dependencies (auth, etc.)
├── settings.py       # Settings management
├── config.py         # Configuration
├── db.py            # Database session
└── time_utils.py    # Timezone utilities

frontend/
├── src/
│   ├── api/         # API client
│   │   ├── auth.ts
│   │   ├── admin.ts
│   │   └── client.ts
│   ├── components/  # React components
│   └── pages/       # Page components
└── (structure assumed based on typical React app)
```

---

## Important Implementation Details

### Authentication
- JWT access tokens (15 min expiry)
- Refresh tokens (7 days, stored in DB)
- Roles: administrator, member, visitor
- Permissions enforced via dependencies: `require_auth`, `require_admin`, `require_member_or_admin`

### Settings System
- Key-value store in DB
- Default settings defined in `backend/settings.py`
- Types: int, bool, string, json
- Tracked who updated and when
- Examples: `scheduler.sync_interval_hours`, `auth.registration_enabled`

### Time Handling
All datetimes use UTC with timezone awareness:
- `now_utc()` - returns timezone-aware datetime
- `ensure_timezone_aware()` - fixes naive datetimes from SQLite
- SQLite doesn't natively support timezones, so datetimes come back naive

### Job System Details
Jobs are database-backed with automatic retry:
- Status: queued → running → completed/failed
- Retry with exponential backoff on failure
- Priority-based execution
- Worker uses `_db_operation_with_retry()` for database lock handling

---

## Current State Summary

**What Works:**
- ✅ User authentication and admin panel
- ✅ Settings management
- ✅ Chart subscriptions
- ✅ Artist subscription system (new, core files created)
- ✅ Job queue and workers
- ✅ Download system

**What's In Progress:**
- ⏳ Album following endpoints (need to create)
- ⏳ Library management endpoints (need to create)
- ⏳ Frontend updates for new subscription system

**Database Migration Needed:**
- Drop `artists.followed` column
- Existing data will be lost (acceptable per user's request)
- No backwards compatibility required

---

## Next Session Priorities

1. **Create album following endpoints** (`backend/routers/albums.py`)
   - Ensure auto-creation of light artist subscription
   
2. **Create library management endpoints**
   - Delete artist/album from library (with files)
   - Cleanup orphaned data

3. **Update any remaining references to `artist.followed`**
   - Search codebase for `.followed` usage
   - Update to use subscription system

4. **Frontend integration**
   - Update API calls
   - Implement new icons (cloud/disk/checkmark)
   - Add mode upgrade/downgrade UI

---

## Development Notes

- **No migration/backwards compatibility needed** - fresh start accepted
- **User wants minimal formatting** - avoid excessive headers, bullets in responses
- **Service-first approach** - business logic in services, routers are thin
- **Transaction management** - services don't commit, routers/jobs control commits
- **Logging** - comprehensive logging at info/debug levels
- **Error handling** - try/catch with rollback, descriptive error messages

---

## Useful Commands

```bash
# Start backend
cd backend
python -m uvicorn main:app --reload

# Start worker
python -m backend.jobs.worker

# Start frontend
cd frontend
npm run dev

# Database
# SQLite DB location: ./data/app.db (or as configured)
```

---

## Contact/Questions
If continuing this project, key things to remember:
1. Subscription modes are the source of truth, not `artist.followed`
2. Light mode = metadata only, Full mode = downloads
3. Unfollowing ≠ Deleting (keeps files)
4. Album follow auto-creates light artist subscription
5. Always respect the router→service→adapter pattern