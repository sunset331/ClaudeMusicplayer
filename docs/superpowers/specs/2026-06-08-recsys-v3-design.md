# Recommendation Engine v3 Design

**Date**: 2026-06-08
**Status**: draft

## Problem

Current engine (v2) has three fundamental weaknesses:

1. **Artist-level feedback only** — liking 1 Eminem song boosts ALL his songs equally. Skipping 5 tracks by an artist still gives them +0.05 per like hit.
2. **No recency decay** — a like from 3 weeks ago and a like from today have identical weight.
3. **Keyword-based genre matching is noise** — matching "rap" in song names against keyword lists is a weak proxy for actual genre. NetEase API returns real genre/style tags that go unused.

## Solution: Hybrid v3 Engine

Three layers: **track-level scoring + recency decay + ε-greedy exploration**

### Layer 1: Track-Level Scoring with Recency

```
final_score = track_feedback(0.35) + tag_match(0.20) + artist_baseline(0.15)
            + history_recency(0.15) + exploration_bonus(0.10) + source(0.05)
```

**Track feedback (0.35)**:
- `song_plays[sid].liked` → +0.30
- `song_plays[sid].skipped` → −0.20
- Similar songs to liked tracks (from `/simi/song` API) → +0.05 ~ +0.15

**Tag matching (0.20)**:
- Use NetEase `/song/detail` genre/style/categories fields (not keyword guessing)
- Build user taste tags from liked songs' actual genres
- Match score = overlap between song tags and user taste tags, normalized

**Artist baseline (0.15)**:
- Retained from v2 but heavily capped — prevents total irrelevance, doesn't dominate

**History recency (0.15)**:
- `weight = base_weight × 0.5^(days_ago / 7)`
- Today = 1.0x, last week = 0.5x, 3 weeks = 0.125x

**Exploration bonus (0.10)**:
- Novelty: songs from new artists not in taste → +0.05
- Source diversity: songs from non-artist sources (charts, genres) → variable +0.01~0.05

**Source (0.05)**:
- Direct artist match: +0.05
- Similar artist: +0.03
- Chart/genre: +0.01

### Layer 2: ε-greedy Bandit

```
Each _play(0) on startup / next after skip:
  if random() < ε:  pick from "unexplored" pool (no play history, high novelty)
  else:              pick from scored top (exploit)
```

- ε starts at 0.15 (15% exploration)
- After like on exploration → ε drops by 0.01 (user taste confirmed)
- After skip on exploration → ε stays, but that artist/genre direction gets negative signal
- After skip on exploitation → ε rises by 0.02 (current taste may be stale)
- ε clamped to [0.05, 0.25]

### Layer 3: Periodic Similarity Expansion

Unchanged from v2 — every 10 songs, fetch `/simi/song` for the most recent 10 played tracks.

## File Changes

| File | Change | Lines |
|------|--------|-------|
| `engine.py` | Refactor `score_rap` / `score_mixed` → unified `score_v3` | ~60 |
| `engine.py` | Add `_extract_genre_tags()` using `/song/detail` | ~20 |
| `engine.py` | Add `decay_weight()` and `build_user_tags()` helpers | ~30 |
| `engine.py` | Add `select_bandit(songs, epsilon)` for ε-greedy selection | ~25 |
| `app.py` | Track `_epsilon` state, adjust on like/skip | ~15 |
| `data/taste.json` | New fields: `user_tags`, `last_explore_skip` | schema only |

## Data Flow

```
[app.py] user likes/skips
    ↓
[_track_play] writes song_plays + updates epsilon
    ↓
[rescore_unplayed] calls score_v3 with recency + track feedback
    ↓
[select_bandit] ε-greedy picks top or exploration
    ↓
_reload_list sorts accordingly
```

## Migration

- `taste.json` automatically gains `user_tags` dict on first v3 run
- Old `artist_weights` preserved but capped at 0.15 contribution
- `history.json` `song_plays` entries are already there — just start reading `liked`/`skipped` flags for scoring
- No manual migration needed

## Non-Goals

- Collaborative filtering (no user community data)
- Audio feature analysis (no audio processing in scope)
- Neural embeddings (overkill for a single-user desktop app)
- Real-time learning (batch rescore on like/skip is sufficient)
