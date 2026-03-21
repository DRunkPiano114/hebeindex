"""
query_generator.py — Generate search queries programmatically from artist YAML.

Data-driven approach: queries are generated per-platform (youtube/bilibili/google),
each tagged with a category for build_search_plan() to group by file.
"""

from __future__ import annotations

from artist_profile import ArtistProfile, load_profile


def generate_queries(profile: ArtistProfile | None = None) -> list[dict]:
    """
    Generate all search queries from artist profile.

    Returns list of {"tool": "youtube"|"bilibili"|"google", "query": str,
                     "page": int, "category": str}
    """
    if profile is None:
        profile = load_profile()

    queries: list[dict] = []
    seen: set[str] = set()

    def add(tool: str, query: str, page: int = 1, category: str = "") -> None:
        key = f"{tool}:{query}:{page}"
        if key not in seen:
            seen.add(key)
            queries.append({"tool": tool, "query": query, "page": page, "category": category})

    primary = profile.artist.names.primary
    english = profile.artist.names.english
    group = profile.group
    has_group = group is not None
    group_name = group.name if group else ""
    group_aliases = group.aliases if group else []

    # --- Personal MV queries ---
    for name in [primary, english]:
        add("youtube", f"{name} MV official", category="personal_mv")
    for album in profile.discography.solo_albums:
        for track in album.tracks:
            add("youtube", f"{primary} {track} MV", category="personal_mv")
    # Recent standalone singles
    for ost in profile.discography.ost_singles:
        add("youtube", f"{primary} {ost.name} MV", category="personal_mv")
    # Bilibili MV
    add("bilibili", f"{primary} MV 官方", category="personal_mv")
    add("bilibili", f"{english} {primary} MV", category="personal_mv")
    # Top tracks on Bilibili
    for album in profile.discography.solo_albums:
        for track in album.tracks[:5]:
            add("bilibili", f"{primary} {track} MV", category="personal_mv")
    # Alias searches for key categories
    for alias in profile.artist.names.aliases:
        add("youtube", f"{alias} MV", category="personal_mv")
        add("bilibili", f"{alias} MV", category="personal_mv")
        add("youtube", f"{alias} 演唱会", category="concerts")
        add("youtube", f"{alias} interview", category="interviews")
    add("google", f"{primary} MV site:bilibili.com", category="personal_mv")

    # --- OST / Singles queries ---
    for ost in profile.discography.ost_singles:
        if ost.source:
            add("youtube", f"{primary} {ost.name} {ost.source}", category="ost_singles")
            if ost.source != ost.name:
                add("youtube", f"{primary} {ost.name} MV", category="ost_singles")
        else:
            add("youtube", f"{primary} {ost.name}", category="ost_singles")
    # Top OST singles on Bilibili
    for ost in profile.discography.ost_singles[:8]:
        add("bilibili", f"{primary} {ost.name}", category="ost_singles")
    # Variety show singles
    for vs in profile.discography.variety_show_singles:
        add("youtube", f"{primary} {vs.name} 单曲 {vs.source}", category="ost_singles")
        add("bilibili", f"{primary} {vs.name} {vs.source}", category="variety")
    add("bilibili", f"{primary} 影视歌曲", category="ost_singles")

    # --- Concert queries ---
    for concert in profile.discography.concerts:
        add("youtube", f"{primary} {concert.name}", category="concerts")
        for alias in concert.aliases:
            add("youtube", f"{primary} {alias}", category="concerts")
        for venue in concert.venues:
            alias_or_name = concert.aliases[0] if concert.aliases else concert.name
            add("youtube", f"{primary} {alias_or_name} {venue}", category="concerts")
        add("bilibili", f"{primary} {concert.name}", category="concerts")
        for alias in concert.aliases:
            add("bilibili", f"{primary} {alias}", category="concerts")
    add("youtube", f"{primary} 演唱会 full", category="concerts")
    add("bilibili", f"{primary} 演唱会 全场", page=1, category="concerts")
    add("bilibili", f"{primary} 演唱会 全场", page=2, category="concerts")
    add("google", f"{primary} 演唱会 全场 site:bilibili.com", category="concerts")
    add("google", f"{primary} {english} concert live", category="concerts")
    # Group concerts
    if has_group:
        for sc in profile.discography.group_concerts:
            add("youtube", f"{sc.name}", category="concerts")
            add("bilibili", f"{sc.name}", category="concerts")
        add("youtube", f"{group_name} 演唱会", category="concerts")
        add("bilibili", f"{group_name} {primary} 演唱会", category="concerts")

    # --- Variety show queries ---
    for show in profile.discography.variety_shows:
        add("youtube", f"{primary} {show.name}", category="variety")
        add("bilibili", f"{primary} {show.name}", category="variety")
    add("youtube", f"{primary} 综艺", category="variety")
    add("youtube", f"{primary} 节目", category="variety")
    if has_group:
        # Group variety show appearances
        for show in profile.discography.variety_shows:
            if show.network:
                add("youtube", f"{group_name} {show.name}", category="variety")
    add("bilibili", f"{primary} 综艺", category="variety")
    add("youtube", f"{primary} 现场 live", category="variety")
    add("bilibili", f"{primary} 现场", category="variety")
    add("google", f"{primary} 综艺 site:bilibili.com", category="variety")
    # Variety show specific performances
    for vs in profile.discography.variety_show_singles:
        add("youtube", f"{primary} {vs.source} {vs.name}", category="variety")
    add("youtube", f"{primary} 跨年 演唱 表演", category="variety")
    add("bilibili", f"{primary} 跨年 跨年晚会", category="variety")

    # --- Interview queries ---
    for name in [primary, english]:
        add("youtube", f"{name} 采访" if name == primary else f"{name} interview", category="interviews")
    add("bilibili", f"{primary} 采访", category="interviews")
    add("bilibili", f"{primary} 专访", category="interviews")
    add("google", f"{english} interview", category="interviews")
    add("google", f"{primary} 深度专访", category="interviews")
    # Album-era interviews
    for album in profile.discography.solo_albums:
        add("youtube", f"{primary} 专访 {album.year} {album.name}", category="interviews")
    # Notable interviewers from YAML
    for interviewer in profile.discography.notable_interviewers:
        add("youtube", f"{primary} {interviewer} 采访", category="interviews")
        add("bilibili", f"{primary} {interviewer}", category="interviews")
    # Interview channels (top 8)
    for channel in profile.discography.interview_channels[:8]:
        add("youtube", f"{primary} {channel}", category="interviews")
        add("bilibili", f"{primary} {channel}", category="interviews")

    # --- Group MV queries ---
    if has_group:
        for name in [group_name] + group_aliases[:1]:
            add("youtube", f"{name} MV official", category="group_mv")
        for mv in profile.discography.group_mvs:
            add("youtube", f"{group_name} {mv} MV", category="group_mv")
        add("bilibili", f"{group_name} MV", category="group_mv")
        # Key group MVs on Bilibili
        for mv in profile.discography.group_mvs[:10]:
            add("bilibili", f"{group_name} {mv} MV", category="group_mv")

    # --- Collaboration queries ---
    for collab in profile.discography.collaborators:
        for song in collab.songs:
            add("youtube", f"{primary} {collab.name} {song}", category="collabs")
            add("bilibili", f"{primary} {collab.name} {song}", category="collabs")
        if not collab.songs:
            add("youtube", f"{primary} {collab.name}", category="collabs")
            add("bilibili", f"{primary} {collab.name}", category="collabs")
        for alias in collab.aliases:
            add("youtube", f"{alias} {primary}", category="collabs")
    add("youtube", f"{primary} 合唱", category="collabs")
    add("bilibili", f"{primary} 合唱", category="collabs")
    add("bilibili", f"{primary} 合作", category="collabs")
    add("google", f"{primary} 合唱 合作 site:bilibili.com", category="collabs")

    return queries


def build_search_plan(profile: ArtistProfile | None = None) -> list[dict]:
    """
    Build a SEARCH_PLAN-compatible structure from generated queries.

    Returns list of file specs compatible with pipeline.py's expected format:
    [{"file_id": int, "output_path": str, "title": str, "description": str, "searches": [...]}]
    """
    if profile is None:
        profile = load_profile()

    queries = generate_queries(profile)
    primary = profile.artist.names.primary

    # Group queries by category
    by_category: dict[str, list[dict]] = {}
    for q in queries:
        cat = q.get("category", "")
        if cat:
            by_category.setdefault(cat, []).append(q)

    plan = []
    for cat in profile.categories:
        searches = by_category.get(cat.key, [])
        plan.append({
            "file_id": cat.id,
            "output_path": cat.output_path,
            "title": f"{primary}{cat.label}",
            "description": cat.description,
            "searches": searches,
        })

    return plan


if __name__ == "__main__":
    profile = load_profile()
    queries = generate_queries(profile)
    print(f"Generated {len(queries)} queries")

    by_tool: dict[str, list] = {}
    for q in queries:
        by_tool.setdefault(q["tool"], []).append(q)
    for tool, qs in sorted(by_tool.items()):
        print(f"  {tool}: {len(qs)}")

    by_cat: dict[str, int] = {}
    for q in queries:
        by_cat[q["category"]] = by_cat.get(q["category"], 0) + 1
    print("\nBy category:")
    for cat, count in sorted(by_cat.items()):
        print(f"  {cat}: {count}")

    print("\n--- Search plan ---")
    plan = build_search_plan(profile)
    for spec in plan:
        print(f"  file_{spec['file_id']}: {spec['title']} ({len(spec['searches'])} searches)")
