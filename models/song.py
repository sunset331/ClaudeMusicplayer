#!/usr/bin/env python3
"""
Song data model — canonical representation replacing bare dicts.

Backward-compatible: Song supports dict-style access (song["songname"],
song.get("_score", 0), etc.) so existing code works without changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Song:
    """Canonical song model — replaces bare dicts across the project.

    Supports dict-like access for backward compatibility with existing
    code that does song["songname"] or song.get("_score", 0).
    """

    songid: int
    songname: str
    singer: list[dict] = field(default_factory=list)  # [{"name": str}, ...]
    albumname: str = ""
    albumid: int = 0
    duration: int = 0  # ms
    url: dict | None = None  # {"url": str, "type": str}
    _sources: list[str] = field(default_factory=list)
    _score: float = 0.0
    _played: bool = False
    _from_simi: bool = False

    # -- computed properties ------------------------------------------------

    @property
    def artist_str(self) -> str:
        """' / '.join of singer names — eliminates 15+ duplicated join patterns."""
        return " / ".join(s.get("name", "") for s in self.singer)

    @property
    def duration_sec(self) -> float:
        """Duration in seconds."""
        return self.duration / 1000.0 if self.duration else 0.0

    # -- dict compatibility ------------------------------------------------

    def __getitem__(self, key: str):
        """song["songname"] → song.songname (backward compat)."""
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __setitem__(self, key: str, value):
        """song["_score"] = 0.95 (backward compat)."""
        setattr(self, key, value)

    def get(self, key: str, default=None):
        """song.get("_score", 0) (backward compat)."""
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize back to dict for JSON persistence."""
        return {
            "songid": self.songid,
            "songname": self.songname,
            "singer": self.singer,
            "albumname": self.albumname,
            "albumid": self.albumid,
            "duration": self.duration,
            "url": self.url,
            "_sources": self._sources,
            "_score": self._score,
            "_played": self._played,
            "_from_simi": self._from_simi,
        }

    # -- factory methods ---------------------------------------------------

    @classmethod
    def from_ncm_song(cls, raw: dict, source: str = "") -> "Song":
        """Build from a NetEase API song item (/search, /artist/songs, /toplist).

        Handles multiple API response formats:
        - /search or /artist/songs: {id, name, ar: [{name}], al: {name, id}, dt}
        - /toplist: {id, name, ar/singer, al/album, dt/duration}
        - /simi/song: {id, name, artists: [{name}], album: {name, id}, duration}
        """
        singer = (
            raw.get("ar", [])
            or raw.get("artists", [])
            or raw.get("singer", [])
            or [{"name": a.get("name", "")} for a in raw.get("ar", [])]
        )
        album = raw.get("al", {}) or raw.get("album", {}) or {}
        return cls(
            songid=raw.get("id", 0),
            songname=raw.get("name", "") or raw.get("songname", ""),
            singer=singer,
            albumname=album.get("name", "") or raw.get("albumname", ""),
            albumid=album.get("id", 0) or raw.get("albumid", 0),
            duration=raw.get("dt", 0) or raw.get("duration", 0),
            _sources=[source] if source else [],
        )

    @classmethod
    def from_dict(cls, d: dict) -> "Song":
        """Hydrate from a JSON-persisted dict (load_candidates, history snapshots)."""
        return cls(
            songid=d.get("songid", 0),
            songname=d.get("songname", ""),
            singer=d.get("singer", []),
            albumname=d.get("albumname", ""),
            albumid=d.get("albumid", 0),
            duration=d.get("duration", 0),
            url=d.get("url"),
            _sources=d.get("_sources", []),
            _score=d.get("_score", 0) or d.get("score", 0),
            _played=d.get("_played", False),
            _from_simi=d.get("_from_simi", False),
        )
