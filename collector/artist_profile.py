"""
artist_profile.py — Load and validate artist.yaml into typed data models.
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


class ArtistInfo(BaseModel):
    names: ArtistNames
    official_channels: list[str]
    labels: list[str]


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


class SHEConcert(BaseModel):
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
    she_concerts: list[SHEConcert] = []
    variety_shows: list[VarietyShow]
    collaborators: list[Collaborator]
    she_mvs: list[str] = []
    western_artist_blacklist: list[str] = []
    other_chinese_artist_blacklist: list[str] = []
    wrong_context_patterns: list[str] = []


class Category(BaseModel):
    id: int
    key: str
    label: str


class ClassificationConfig(BaseModel):
    priority: list[str]


class ArtistProfile(BaseModel):
    artist: ArtistInfo
    group: GroupInfo
    discography: Discography
    categories: list[Category]
    classification: ClassificationConfig

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

    def all_she_concert_names(self) -> list[str]:
        return [c.name for c in self.discography.she_concerts]

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

    def she_patterns(self) -> re.Pattern:
        """Compiled regex for matching S.H.E references."""
        patterns = [
            r"(?<![A-Za-z])S\.H\.E(?![A-Za-z])",
            r"(?<![A-Za-z])S\.H\.E\.",
            r"(?<![A-Za-z])SHE(?![A-Za-z])",
            r"(?<![A-Za-z])S\s+H\s+E(?![A-Za-z])",
        ]
        return re.compile("|".join(patterns), re.IGNORECASE)


def load_profile(path: str | Path | None = None) -> ArtistProfile:
    """Load artist.yaml and return a validated ArtistProfile."""
    if path is None:
        path = Path(__file__).parent / "artist.yaml"
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ArtistProfile(**data)
