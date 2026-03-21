"""
artist_profile.py — Load and validate artist YAML into typed data models.

Fully generic: works for any artist. Group membership is optional.
"""

from __future__ import annotations

import re
from pathlib import Path
import yaml
from pydantic import BaseModel


class ArtistNames(BaseModel):
    primary: str
    english: str
    aliases: list[str]


class Channel(BaseModel):
    platform: str
    id: str
    name: str = ""


class ArtistInfo(BaseModel):
    names: ArtistNames
    official_channels: list[str]
    labels: list[str]
    birth_year: int | None = None
    genre: str | None = None
    awards: list[str] = []
    social_links: dict[str, str] = {}
    channels: list[Channel] = []


class GroupInfo(BaseModel):
    name: str
    aliases: list[str]
    members: list[str]
    member_names: list[str]


class Album(BaseModel):
    name: str
    year: int
    tracks: list[str]


class OSTSingle(BaseModel):
    name: str
    source: str
    year: int


class VarietyShowSingle(BaseModel):
    name: str
    source: str
    year: int


class Concert(BaseModel):
    name: str
    years: str
    aliases: list[str] = []
    venues: list[str] = []


class GroupConcert(BaseModel):
    name: str
    years: str


class VarietyShow(BaseModel):
    name: str
    network: str = ""


class Collaborator(BaseModel):
    name: str
    aliases: list[str] = []
    songs: list[str] = []


class Discography(BaseModel):
    solo_albums: list[Album]
    ost_singles: list[OSTSingle]
    variety_show_singles: list[VarietyShowSingle] = []
    concerts: list[Concert]
    group_concerts: list[GroupConcert] = []
    variety_shows: list[VarietyShow]
    collaborators: list[Collaborator]
    group_mvs: list[str] = []
    venues: list[str] = []
    interview_channels: list[str] = []
    notable_interviewers: list[str] = []
    western_artist_blacklist: list[str] = []
    other_chinese_artist_blacklist: list[str] = []
    wrong_context_patterns: list[str] = []


class Category(BaseModel):
    id: int
    key: str
    label: str
    sub: str = ""
    output_path: str = ""
    description: str = ""


class ClassificationConfig(BaseModel):
    priority: list[str]


class ArtistProfile(BaseModel):
    artist: ArtistInfo
    group: GroupInfo | None = None
    discography: Discography
    categories: list[Category]
    classification: ClassificationConfig

    def slug(self) -> str:
        """URL-safe slug derived from the english name."""
        return self.artist.names.english.lower().replace(" ", "_").replace(".", "")

    def all_artist_names(self) -> list[str]:
        """All name variants for the artist (primary, english, aliases)."""
        return [self.artist.names.primary, self.artist.names.english] + self.artist.names.aliases

    def all_track_names(self) -> list[str]:
        """All known track names across all solo albums."""
        tracks = []
        for album in self.discography.solo_albums:
            tracks.extend(album.tracks)
        return tracks

    def all_ost_names(self) -> list[str]:
        """All OST/single song names."""
        return [s.name for s in self.discography.ost_singles]

    def all_concert_names(self) -> list[str]:
        """All concert names + aliases."""
        names = []
        for c in self.discography.concerts:
            names.append(c.name)
            names.extend(c.aliases)
        return names

    def all_group_concert_names(self) -> list[str]:
        return [c.name for c in self.discography.group_concerts]

    def all_variety_show_names(self) -> list[str]:
        return [v.name for v in self.discography.variety_shows]

    def category_by_key(self, key: str) -> Category | None:
        for c in self.categories:
            if c.key == key:
                return c
        return None

    def category_by_id(self, file_id: int) -> Category | None:
        for c in self.categories:
            if c.id == file_id:
                return c
        return None

    def category_file_map(self) -> dict[str, int]:
        """Build category key -> file_id mapping from categories list."""
        return {c.key: c.id for c in self.categories}

    def file_ids(self) -> list[int]:
        """All category file IDs."""
        return [c.id for c in self.categories]

    def group_patterns(self) -> re.Pattern | None:
        """Compiled regex for matching group name references. None if no group."""
        if self.group is None:
            return None
        group_name = self.group.name
        aliases = self.group.aliases
        patterns = []
        for name in [group_name] + aliases:
            escaped = re.escape(name)
            patterns.append(rf"(?<![A-Za-z]){escaped}(?![A-Za-z])")
        return re.compile("|".join(patterns), re.IGNORECASE)


def load_profile(path: str | Path | None = None) -> ArtistProfile:
    """Load artist YAML and return a validated ArtistProfile.

    Default search order: artists/ directory, then collector root.
    """
    if path is None:
        artists_dir = Path(__file__).parent / "artists"
        root_path = Path(__file__).parent / "artist.yaml"
        # Prefer artists/ directory
        candidates = sorted(artists_dir.glob("*.yaml")) if artists_dir.exists() else []
        if candidates:
            path = candidates[0]
        elif root_path.exists():
            path = root_path
        else:
            raise FileNotFoundError(
                "No artist YAML found. Place one in artists/ or as artist.yaml"
            )
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ArtistProfile(**data)
