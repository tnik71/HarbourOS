"""Episode Manager service - compares Plex library against central episode DB."""

import json
import os
import re
import urllib.request

from . import plex_service

EPISODE_DB_API = "https://harbouros.eu/db/api.php"
EPISODE_DB_SECRET = "c65f3345d88f8da55c76fd7d7a032e39"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
LOCAL_DB_PATH = os.path.join(DATA_DIR, "episode-db.json")
SCAN_RESULTS_PATH = os.path.join(DATA_DIR, "scan-results.json")

# In-memory cache
_episode_db = None
_scan_results = None


def _load_scan_results():
    """Load scan results from disk into memory cache."""
    global _scan_results
    if _scan_results is not None:
        return _scan_results
    try:
        with open(SCAN_RESULTS_PATH, "r") as f:
            _scan_results = json.load(f)
        return _scan_results
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_scan_results(results):
    """Save scan results to disk."""
    _ensure_data_dir()
    with open(SCAN_RESULTS_PATH, "w") as f:
        json.dump(results, f)


def _ensure_data_dir():
    """Create data directory if it doesn't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_db():
    """Load episode database from local cache into memory."""
    global _episode_db
    if _episode_db is not None:
        return _episode_db

    if not os.path.exists(LOCAL_DB_PATH):
        return None

    try:
        with open(LOCAL_DB_PATH, "r") as f:
            _episode_db = json.load(f)
        return _episode_db
    except (json.JSONDecodeError, OSError):
        return None


def _normalize_title(title):
    """Normalize a title for fuzzy matching."""
    s = title.lower()
    # Remove year suffixes like (2024) and country codes like (US), (UK)
    s = re.sub(r'\s*\(\d{4}\)\s*$', '', s)
    s = re.sub(r'\s*\([a-z]{2,3}\)\s*$', '', s)
    # Remove common articles
    s = re.sub(r'^(the|a|an)\s+', '', s)
    # Remove punctuation and extra whitespace
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _get_show_year(show):
    """Extract the premiere year from a show's first episode air date."""
    for season in show.get("seasons", []):
        for ep in season.get("episodes", []):
            air_date = ep.get("air_date")
            if air_date:
                return air_date[:4]
    return None


def update_episode_db():
    """Download episode data for this Pi's Plex shows from the API."""
    global _episode_db

    if os.environ.get("HARBOUROS_DEV"):
        return _mock_update_db()

    _ensure_data_dir()

    try:
        # Get this Pi's Plex shows to know which TMDB IDs we need
        plex_shows = _get_plex_tv_shows()
        tmdb_ids = [s["tmdb_id"] for s in plex_shows if s.get("tmdb_id")]

        if not tmdb_ids:
            return False, "No Plex shows with TMDB IDs found."

        # Query the API for just these shows (~4MB instead of 167MB)
        ids_str = ",".join(str(i) for i in tmdb_ids)
        url = (
            f"{EPISODE_DB_API}?key={EPISODE_DB_SECRET}"
            f"&action=lookup&ids={ids_str}"
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "HarbourOS/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Save to local cache
        with open(LOCAL_DB_PATH, "w") as f:
            json.dump(data, f)

        _episode_db = data
        return True, f"Database updated: v{data.get('version', 'unknown')} ({data.get('show_count', 0)} shows)"
    except Exception as e:
        return False, f"Failed to update database: {e}"


def _mock_update_db():
    """Mock database update for dev mode."""
    global _episode_db
    _ensure_data_dir()
    _episode_db = _mock_episode_db()
    with open(LOCAL_DB_PATH, "w") as f:
        json.dump(_episode_db, f)
    return True, f"Database updated: v{_episode_db['version']} ({_episode_db['show_count']} shows)"


def get_db_info():
    """Return info about the local episode database."""
    db = _load_db()
    if db is None:
        return {
            "available": False,
            "version": None,
            "show_count": 0,
            "total_episodes": 0,
        }
    return {
        "available": True,
        "version": db.get("version"),
        "show_count": db.get("show_count", 0),
        "total_episodes": db.get("total_episodes", 0),
    }


def _get_plex_tv_shows():
    """Fetch all TV shows from Plex library."""
    if os.environ.get("HARBOUROS_DEV"):
        return _mock_plex_shows()

    token = plex_service.get_plex_token()
    if not token:
        return []

    headers = {
        "X-Plex-Token": token,
        "Accept": "application/json",
    }

    shows = []
    try:
        # Get all library sections
        req = urllib.request.Request(
            plex_service.PLEX_BASE_URL + "/library/sections",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            sections = data.get("MediaContainer", {}).get("Directory", [])

        # Get shows from each TV show library
        for section in sections:
            if section.get("type") != "show":
                continue
            key = section.get("key")
            req = urllib.request.Request(
                plex_service.PLEX_BASE_URL
                + f"/library/sections/{key}/all?type=2&includeGuids=1",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                for show in data.get("MediaContainer", {}).get("Metadata", []):
                    tmdb_id = None
                    for g in show.get("Guid", []):
                        gid = g.get("id", "")
                        if gid.startswith("tmdb://"):
                            try:
                                tmdb_id = int(gid[7:])
                            except ValueError:
                                pass
                            break
                    shows.append({
                        "rating_key": show.get("ratingKey"),
                        "title": show.get("title"),
                        "year": show.get("year"),
                        "tmdb_id": tmdb_id,
                        "library": section.get("title"),
                    })
    except Exception:
        pass

    return shows


def _get_plex_episodes(rating_key):
    """Fetch all episodes for a show from Plex."""
    if os.environ.get("HARBOUROS_DEV"):
        return _mock_plex_episodes(rating_key)

    token = plex_service.get_plex_token()
    if not token:
        return []

    headers = {
        "X-Plex-Token": token,
        "Accept": "application/json",
    }

    episodes = []
    try:
        # Get seasons
        req = urllib.request.Request(
            plex_service.PLEX_BASE_URL + f"/library/metadata/{rating_key}/children",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            seasons = data.get("MediaContainer", {}).get("Metadata", [])

        for season in seasons:
            season_key = season.get("ratingKey")
            season_num = season.get("index", 0)
            if season_num == 0:
                continue  # Skip specials

            # Get episodes in this season
            req = urllib.request.Request(
                plex_service.PLEX_BASE_URL + f"/library/metadata/{season_key}/children",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                for ep in data.get("MediaContainer", {}).get("Metadata", []):
                    episodes.append({
                        "season": season_num,
                        "episode": ep.get("index", 0),
                    })
    except Exception:
        pass

    return episodes


def _match_show(plex_title, db, plex_year=None, plex_tmdb_id=None,
                tmdb_lookup=None):
    """Match a Plex show to a DB entry. Prefers TMDB ID, falls back to title."""
    # Direct TMDB ID match — fast and unambiguous
    if plex_tmdb_id and tmdb_lookup:
        match = tmdb_lookup.get(plex_tmdb_id)
        if match:
            return match
        # Has TMDB ID but not in DB — report as unmatched so it gets added
        return None

    # Fall back to title matching for shows without TMDB ID
    normalized_plex = _normalize_title(plex_title)
    candidates = []

    for show in db.get("shows", []):
        if show["title"].lower() == plex_title.lower():
            candidates.append(show)
            continue
        if _normalize_title(show["title"]) == normalized_plex:
            candidates.append(show)
            continue
        for alias in show.get("aliases", []):
            if _normalize_title(alias) == normalized_plex:
                candidates.append(show)
                break

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Multiple matches — disambiguate by year
    if plex_year:
        for show in candidates:
            show_year = _get_show_year(show)
            if show_year and str(show_year) == str(plex_year):
                return show

    return candidates[0]


def _request_missing_shows(tmdb_ids):
    """Ask harbouros.eu to add missing shows to the central episode DB."""
    if not tmdb_ids or os.environ.get("HARBOUROS_DEV"):
        return

    try:
        url = f"{EPISODE_DB_API}?key={EPISODE_DB_SECRET}&action=add-shows"
        body = json.dumps({"tmdb_ids": tmdb_ids}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def scan_plex_library():
    """Full scan: fetch Plex shows, match to DB, compute missing episodes."""
    global _scan_results

    db = _load_db()
    if db is None:
        return False, "No episode database. Update the database first."

    plex_shows = _get_plex_tv_shows()
    if not plex_shows:
        return False, "No TV shows found in Plex library."

    # Build TMDB ID lookup for O(1) matching
    tmdb_lookup = {
        show["tmdb_id"]: show
        for show in db.get("shows", [])
        if show.get("tmdb_id")
    }

    results = []
    for plex_show in plex_shows:
        db_show = _match_show(
            plex_show["title"], db,
            plex_year=plex_show.get("year"),
            plex_tmdb_id=plex_show.get("tmdb_id"),
            tmdb_lookup=tmdb_lookup,
        )
        if db_show is None:
            results.append({
                "plex_title": plex_show["title"],
                "rating_key": plex_show["rating_key"],
                "library": plex_show.get("library", ""),
                "matched": False,
                "tmdb_id": plex_show.get("tmdb_id"),
                "db_title": None,
                "status": None,
                "total_episodes": 0,
                "local_episodes": 0,
                "missing_count": 0,
                "completion_pct": 0,
                "seasons": [],
            })
            continue

        # Fetch episodes from Plex for this show
        plex_episodes = _get_plex_episodes(plex_show["rating_key"])
        plex_ep_set = {(e["season"], e["episode"]) for e in plex_episodes}

        # Compare against DB
        today = _today_str()
        seasons_info = []
        total_db = 0
        total_local = 0

        for db_season in db_show.get("seasons", []):
            season_num = db_season["number"]
            season_eps = db_season.get("episodes", [])
            aired_eps = [
                e for e in season_eps
                if e.get("air_date") and e["air_date"] <= today
            ]
            not_aired_eps = [
                e for e in season_eps
                if not e.get("air_date") or e["air_date"] > today
            ]

            local_in_season = sum(
                1 for e in aired_eps
                if (season_num, e["number"]) in plex_ep_set
            )
            missing_in_season = [
                {
                    "episode": e["number"],
                    "name": e.get("name", f"Episode {e['number']}"),
                    "air_date": e.get("air_date"),
                }
                for e in aired_eps
                if (season_num, e["number"]) not in plex_ep_set
            ]

            total_db += len(aired_eps)
            total_local += local_in_season

            seasons_info.append({
                "number": season_num,
                "total_aired": len(aired_eps),
                "local": local_in_season,
                "missing": missing_in_season,
                "not_aired": len(not_aired_eps),
            })

        completion = round(total_local / total_db * 100) if total_db > 0 else 0

        results.append({
            "plex_title": plex_show["title"],
            "rating_key": plex_show["rating_key"],
            "library": plex_show.get("library", ""),
            "matched": True,
            "tmdb_id": db_show.get("tmdb_id"),
            "db_title": db_show.get("title"),
            "status": db_show.get("status"),
            "total_episodes": total_db,
            "local_episodes": total_local,
            "missing_count": total_db - total_local,
            "completion_pct": completion,
            "seasons": seasons_info,
        })

    # Sort: incomplete first, then by completion percentage
    results.sort(key=lambda s: (
        not s["matched"],  # Unmatched last
        s["completion_pct"] == 100,  # Complete last
        s["completion_pct"],  # Lower completion first
    ))

    _scan_results = results
    _save_scan_results(results)
    matched = sum(1 for r in results if r["matched"])
    unmatched = len(results) - matched

    # Request missing shows to be added to the central DB
    missing_tmdb_ids = [
        r["tmdb_id"] for r in results
        if not r["matched"] and r.get("tmdb_id")
    ]
    add_msg = ""
    if missing_tmdb_ids:
        add_result = _request_missing_shows(missing_tmdb_ids)
        if add_result and add_result.get("added", 0) > 0:
            add_msg = (
                f". {add_result['added']} new shows submitted to database"
                " — update DB and rescan to match them"
            )

    return True, f"Scanned {len(results)} shows ({matched} matched, {unmatched} unmatched{add_msg})"


def get_shows_status():
    """Return the latest scan results."""
    results = _scan_results if _scan_results is not None else _load_scan_results()
    if results is None:
        return {"scanned": False, "shows": []}
    return {
        "scanned": True,
        "shows": [
            {
                "plex_title": s["plex_title"],
                "rating_key": s["rating_key"],
                "library": s.get("library", ""),
                "matched": s["matched"],
                "db_title": s.get("db_title"),
                "status": s.get("status"),
                "total_episodes": s["total_episodes"],
                "local_episodes": s["local_episodes"],
                "missing_count": s["missing_count"],
                "completion_pct": s["completion_pct"],
            }
            for s in results
        ],
    }


def get_missing_episodes(rating_key):
    """Get detailed missing episode info for a specific show."""
    results = _scan_results if _scan_results is not None else _load_scan_results()
    if results is None:
        return None

    for show in results:
        if show["rating_key"] == rating_key:
            return {
                "plex_title": show["plex_title"],
                "db_title": show.get("db_title"),
                "status": show.get("status"),
                "matched": show["matched"],
                "total_episodes": show["total_episodes"],
                "local_episodes": show["local_episodes"],
                "missing_count": show["missing_count"],
                "completion_pct": show["completion_pct"],
                "seasons": show.get("seasons", []),
            }

    return None


def _today_str():
    """Get today's date as YYYY-MM-DD string."""
    from datetime import date
    return date.today().isoformat()


# --- Mock data for dev mode ---

def _mock_episode_db():
    """Return a sample episode database for development."""
    return {
        "version": "2026-02-24",
        "show_count": 6,
        "total_episodes": 259,
        "shows": [
            {
                "tmdb_id": 1396,
                "title": "Breaking Bad",
                "aliases": ["breaking bad"],
                "status": "Ended",
                "total_episodes": 62,
                "seasons": [
                    {"number": 1, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2008-01-20"}
                        for i in range(1, 8)
                    ]},
                    {"number": 2, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2009-03-08"}
                        for i in range(1, 14)
                    ]},
                    {"number": 3, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2010-03-21"}
                        for i in range(1, 14)
                    ]},
                    {"number": 4, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2011-07-17"}
                        for i in range(1, 14)
                    ]},
                    {"number": 5, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2012-07-15"}
                        for i in range(1, 17)
                    ]},
                ],
            },
            {
                "tmdb_id": 94997,
                "title": "House of the Dragon",
                "aliases": ["house of the dragon", "house dragon"],
                "status": "Returning Series",
                "total_episodes": 18,
                "seasons": [
                    {"number": 1, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2022-08-21"}
                        for i in range(1, 11)
                    ]},
                    {"number": 2, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2024-06-16"}
                        for i in range(1, 9)
                    ]},
                ],
            },
            {
                "tmdb_id": 136315,
                "title": "The Bear",
                "aliases": ["bear"],
                "status": "Returning Series",
                "total_episodes": 38,
                "seasons": [
                    {"number": 1, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2022-06-23"}
                        for i in range(1, 9)
                    ]},
                    {"number": 2, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2023-06-22"}
                        for i in range(1, 11)
                    ]},
                    {"number": 3, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2024-06-26"}
                        for i in range(1, 11)
                    ]},
                    {"number": 4, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2025-06-25"}
                        for i in range(1, 11)
                    ]},
                ],
            },
            {
                "tmdb_id": 100088,
                "title": "The Last of Us",
                "aliases": ["last of us", "tlou"],
                "status": "Returning Series",
                "total_episodes": 16,
                "seasons": [
                    {"number": 1, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2023-01-15"}
                        for i in range(1, 10)
                    ]},
                    {"number": 2, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2025-04-13"}
                        for i in range(1, 8)
                    ]},
                ],
            },
            {
                "tmdb_id": 97186,
                "title": "Severance",
                "aliases": ["severance"],
                "status": "Returning Series",
                "total_episodes": 20,
                "seasons": [
                    {"number": 1, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2022-02-18"}
                        for i in range(1, 10)
                    ]},
                    {"number": 2, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2025-01-17"}
                        for i in range(1, 11)
                    ]},
                ],
            },
            {
                "tmdb_id": 84773,
                "title": "The Lord of the Rings: The Rings of Power",
                "aliases": ["lord of the rings rings of power", "rings of power"],
                "status": "Returning Series",
                "total_episodes": 16,
                "seasons": [
                    {"number": 1, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2022-09-01"}
                        for i in range(1, 9)
                    ]},
                    {"number": 2, "episodes": [
                        {"number": i, "name": f"Episode {i}", "air_date": "2024-08-29"}
                        for i in range(1, 9)
                    ]},
                ],
            },
        ],
    }


def _mock_plex_shows():
    """Return mock Plex TV shows for dev mode."""
    return [
        {"rating_key": "1001", "title": "Breaking Bad", "year": 2008, "tmdb_id": 1396, "library": "TV Shows"},
        {"rating_key": "1002", "title": "The Bear", "year": 2022, "tmdb_id": 136315, "library": "TV Shows"},
        {"rating_key": "1003", "title": "Severance", "year": 2022, "tmdb_id": 97186, "library": "TV Shows"},
        {"rating_key": "1004", "title": "House of the Dragon", "year": 2022, "tmdb_id": 94997, "library": "TV Shows"},
        {"rating_key": "1005", "title": "The Last of Us", "year": 2023, "tmdb_id": 100088, "library": "TV Shows"},
        {"rating_key": "1006", "title": "Slow Horses", "year": 2022, "tmdb_id": 99246, "library": "TV Shows"},
    ]


def _mock_plex_episodes(rating_key):
    """Return mock Plex episodes for dev mode - simulates partial collections."""
    mock_data = {
        # Breaking Bad - complete
        "1001": [{"season": s, "episode": e}
                 for s in range(1, 6)
                 for e in range(1, {1: 8, 2: 14, 3: 14, 4: 14, 5: 17}.get(s, 1))],
        # The Bear - seasons 1-2 complete, season 3 partial, season 4 missing
        "1002": (
            [{"season": 1, "episode": e} for e in range(1, 9)] +
            [{"season": 2, "episode": e} for e in range(1, 11)] +
            [{"season": 3, "episode": e} for e in range(1, 7)]
        ),
        # Severance - season 1 complete, season 2 partial
        "1003": (
            [{"season": 1, "episode": e} for e in range(1, 10)] +
            [{"season": 2, "episode": e} for e in range(1, 6)]
        ),
        # House of the Dragon - season 1 complete, season 2 missing half
        "1004": (
            [{"season": 1, "episode": e} for e in range(1, 11)] +
            [{"season": 2, "episode": e} for e in range(1, 5)]
        ),
        # The Last of Us - season 1 complete, no season 2
        "1005": [{"season": 1, "episode": e} for e in range(1, 10)],
        # Slow Horses - not in DB, won't match
        "1006": [{"season": 1, "episode": e} for e in range(1, 7)],
    }
    return mock_data.get(rating_key, [])
