"""Episode Manager service - compares Plex library against central episode DB."""

import gzip
import json
import os
import re
import urllib.request

from . import plex_service

EPISODE_DB_URL = "https://harbouros.eu/db/episode-db.json.gz"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
LOCAL_DB_PATH = os.path.join(DATA_DIR, "episode-db.json")

# In-memory cache
_episode_db = None
_scan_results = None


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
    # Remove year suffixes like (2024)
    s = re.sub(r'\s*\(\d{4}\)\s*$', '', s)
    # Remove common articles
    s = re.sub(r'^(the|a|an)\s+', '', s)
    # Remove punctuation and extra whitespace
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def update_episode_db():
    """Download the latest episode database from harbouros.eu."""
    global _episode_db

    if os.environ.get("HARBOUROS_DEV"):
        return _mock_update_db()

    _ensure_data_dir()

    try:
        req = urllib.request.Request(
            EPISODE_DB_URL,
            headers={
                "Accept-Encoding": "gzip",
                "User-Agent": "HarbourOS/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            compressed = resp.read()
            raw = gzip.decompress(compressed)
            data = json.loads(raw.decode("utf-8"))

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
                plex_service.PLEX_BASE_URL + f"/library/sections/{key}/all?type=2",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                for show in data.get("MediaContainer", {}).get("Metadata", []):
                    shows.append({
                        "rating_key": show.get("ratingKey"),
                        "title": show.get("title"),
                        "year": show.get("year"),
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


def _match_show(plex_title, db):
    """Match a Plex show title to a central DB entry."""
    normalized_plex = _normalize_title(plex_title)

    # Exact title match (case-insensitive)
    for show in db.get("shows", []):
        if show["title"].lower() == plex_title.lower():
            return show

    # Normalized match
    for show in db.get("shows", []):
        if _normalize_title(show["title"]) == normalized_plex:
            return show

    # Alias match
    for show in db.get("shows", []):
        if normalized_plex in show.get("aliases", []):
            return show

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

    results = []
    for plex_show in plex_shows:
        db_show = _match_show(plex_show["title"], db)
        if db_show is None:
            results.append({
                "plex_title": plex_show["title"],
                "rating_key": plex_show["rating_key"],
                "library": plex_show.get("library", ""),
                "matched": False,
                "tmdb_id": None,
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
    matched = sum(1 for r in results if r["matched"])
    return True, f"Scanned {len(results)} shows ({matched} matched, {len(results) - matched} unmatched)"


def get_shows_status():
    """Return the latest scan results."""
    if _scan_results is None:
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
            for s in _scan_results
        ],
    }


def get_missing_episodes(rating_key):
    """Get detailed missing episode info for a specific show."""
    if _scan_results is None:
        return None

    for show in _scan_results:
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
        {"rating_key": "1001", "title": "Breaking Bad", "year": 2008, "library": "TV Shows"},
        {"rating_key": "1002", "title": "The Bear", "year": 2022, "library": "TV Shows"},
        {"rating_key": "1003", "title": "Severance", "year": 2022, "library": "TV Shows"},
        {"rating_key": "1004", "title": "House of the Dragon", "year": 2022, "library": "TV Shows"},
        {"rating_key": "1005", "title": "The Last of Us", "year": 2023, "library": "TV Shows"},
        {"rating_key": "1006", "title": "Slow Horses", "year": 2022, "library": "TV Shows"},
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
