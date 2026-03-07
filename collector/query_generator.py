"""
query_generator.py — Generate search queries programmatically from artist.yaml.

Replaces the 170+ hand-written queries in search_plan.py with a data-driven
approach. Queries are generated per-platform (youtube/bilibili/google) and
are NOT pre-assigned to categories — classification happens after search.
"""

from __future__ import annotations

from artist_profile import ArtistProfile, load_profile


def generate_queries(profile: ArtistProfile | None = None) -> list[dict]:
    """
    Generate all search queries from artist profile.

    Returns list of {"tool": "youtube"|"bilibili"|"google", "query": str, "page": int}
    """
    if profile is None:
        profile = load_profile()

    queries: list[dict] = []
    seen: set[str] = set()

    def add(tool: str, query: str, page: int = 1) -> None:
        key = f"{tool}:{query}:{page}"
        if key not in seen:
            seen.add(key)
            queries.append({"tool": tool, "query": query, "page": page})

    names = profile.all_artist_names()
    primary = profile.artist.names.primary
    english = profile.artist.names.english
    group_name = profile.group.name
    group_aliases = profile.group.aliases

    # --- Personal MV queries ---
    for name in [primary, english]:
        add("youtube", f"{name} MV official")
    for album in profile.discography.solo_albums:
        for track in album.tracks:
            add("youtube", f"{primary} {track} MV")
    # Recent standalone singles
    for ost in profile.discography.ost_singles:
        add("youtube", f"{primary} {ost.name} MV")
    # Bilibili MV
    add("bilibili", f"{primary} MV 官方")
    add("bilibili", f"Hebe {primary} MV")
    add("bilibili", f"{primary} 小幸运 官方")
    for album in profile.discography.solo_albums:
        # Bilibili top tracks per album
        for track in album.tracks[:3]:
            add("bilibili", f"{primary} {track} MV")

    # --- OST / Singles queries ---
    for ost in profile.discography.ost_singles:
        if ost.source:
            add("youtube", f"{primary} {ost.name} {ost.source}")
            if ost.source != ost.name:
                add("youtube", f"{primary} {ost.name} MV")
        else:
            add("youtube", f"{primary} {ost.name}")
    add("youtube", f"{english} A Little Happiness")
    # Variety show singles
    for vs in profile.discography.variety_show_singles:
        add("youtube", f"{primary} {vs.name} 单曲 {vs.source}")
    add("bilibili", f"{primary} 小幸运")
    add("bilibili", f"{primary} 影视歌曲")
    add("bilibili", f"{primary} 梦想的声音 单曲 数字发行")

    # --- Concert queries ---
    for concert in profile.discography.concerts:
        add("youtube", f"{primary} {concert.name}")
        for alias in concert.aliases:
            add("youtube", f"{primary} {alias}")
        for venue in concert.venues:
            add("youtube", f"{primary} {concert.aliases[0] if concert.aliases else concert.name} {venue}")
        add("bilibili", f"{primary} {concert.name}")
        for alias in concert.aliases:
            add("bilibili", f"{primary} {alias}")
    add("youtube", f"{primary} 演唱会 full")
    add("youtube", f"{english} IF Only concert")
    add("bilibili", f"{primary} 演唱会 全场", page=1)
    add("bilibili", f"{primary} 演唱会 全场", page=2)
    add("google", f"{primary} 演唱会 全场 site:bilibili.com")
    # S.H.E concerts
    for sc in profile.discography.she_concerts:
        add("youtube", f"{sc.name}")
        add("bilibili", f"{sc.name}")
    add("youtube", f"SHE 演唱会")
    add("bilibili", f"SHE {primary} 演唱会")

    # --- Variety show queries ---
    for show in profile.discography.variety_shows:
        add("youtube", f"{primary} {show.name}")
        add("bilibili", f"{primary} {show.name}")
    add("youtube", f"{primary} 综艺")
    add("youtube", f"{primary} 节目")
    add("youtube", f"SHE 康熙来了")
    add("bilibili", f"梦想的声音 {primary}", page=1)
    add("bilibili", f"梦想的声音 {primary}", page=2)
    add("bilibili", f"{primary} 综艺")
    # Variety show specific performances
    for vs in profile.discography.variety_show_singles:
        add("youtube", f"{primary} {vs.source} {vs.name}")
    add("youtube", f"{primary} 跨年 演唱 表演")
    add("bilibili", f"{primary} 跨年 跨年晚会")
    add("youtube", f"{primary} 我想和你唱 第三季 2018")
    add("bilibili", f"{primary} 我想和你唱 2018 湖南卫视")

    # --- Interview queries ---
    for name in [primary, english]:
        add("youtube", f"{name} 采访" if name == primary else f"{name} interview")
    add("youtube", f"{primary} 专访 2020")
    add("youtube", f"{primary} 专访 2021")
    add("youtube", f"{primary} 专访 2023")
    add("youtube", f"{primary} 专访 2025 田调 巡演")
    add("bilibili", f"{primary} 采访")
    add("bilibili", f"{primary} 专访")
    add("bilibili", f"{primary} 金曲奖 专访")
    add("google", f"{english} interview 2021 2022")
    add("google", f"{primary} 深度专访")
    # Album-era interviews
    for album in profile.discography.solo_albums:
        add("youtube", f"{primary} 专访 {album.year} {album.name}")
    add("youtube", f"Hebe {primary} 访谈")
    # Specific interviewers
    add("youtube", f"{primary} 理科太太 采访")
    add("youtube", f"{primary} 唐绮阳 访谈")
    add("bilibili", f"{primary} 理科太太")

    # --- S.H.E MV queries ---
    for name in [group_name] + group_aliases[:1]:
        add("youtube", f"{name} MV official")
    for mv in profile.discography.she_mvs:
        add("youtube", f"SHE {mv} MV")
    add("bilibili", f"SHE MV")
    # Key S.H.E MVs on Bilibili
    for mv in profile.discography.she_mvs[:10]:
        add("bilibili", f"SHE {mv} MV")

    # --- Collaboration queries ---
    for collab in profile.discography.collaborators:
        for song in collab.songs:
            add("youtube", f"{primary} {collab.name} {song}")
            add("bilibili", f"{primary} {collab.name} {song}")
        if not collab.songs:
            add("youtube", f"{primary} {collab.name}")
            add("bilibili", f"{primary} {collab.name}")
        for alias in collab.aliases:
            add("youtube", f"{alias} {primary}")
    add("youtube", f"{primary} 合唱")
    add("bilibili", f"{primary} 合唱")
    add("bilibili", f"{primary} 合作")

    return queries


def compare_with_search_plan(profile: ArtistProfile | None = None) -> dict:
    """Compare generated queries with search_plan.py for coverage analysis."""
    from search_plan import SEARCH_PLAN

    if profile is None:
        profile = load_profile()

    generated = generate_queries(profile)
    gen_set = {(q["tool"], q["query"]) for q in generated}

    plan_queries = []
    for file_spec in SEARCH_PLAN:
        for s in file_spec["searches"]:
            plan_queries.append((s["tool"], s["query"]))
    plan_set = set(plan_queries)

    return {
        "generated_count": len(generated),
        "plan_count": len(plan_queries),
        "plan_unique": len(plan_set),
        "overlap": len(gen_set & plan_set),
        "only_in_generated": len(gen_set - plan_set),
        "only_in_plan": len(plan_set - gen_set),
        "missing_from_generated": sorted(plan_set - gen_set),
    }


if __name__ == "__main__":
    profile = load_profile()
    queries = generate_queries(profile)
    print(f"Generated {len(queries)} queries")

    by_tool = {}
    for q in queries:
        by_tool.setdefault(q["tool"], []).append(q)
    for tool, qs in sorted(by_tool.items()):
        print(f"  {tool}: {len(qs)}")

    print("\n--- Coverage comparison with search_plan.py ---")
    stats = compare_with_search_plan(profile)
    for k, v in stats.items():
        if k != "missing_from_generated":
            print(f"  {k}: {v}")
    if stats["missing_from_generated"]:
        print(f"\n  Top 10 queries only in search_plan.py:")
        for tool, query in stats["missing_from_generated"][:10]:
            print(f"    [{tool}] {query}")
