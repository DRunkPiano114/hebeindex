#!/usr/bin/env python3
"""
create_artist.py — Generate a new artist YAML from scratch using Claude CLI.

Uses the existing hebe.yaml as a format reference and Claude's knowledge
to generate a complete artist profile for a new artist.

Usage:
    uv run python create_artist.py "周杰伦" "Jay Chou"
    uv run python create_artist.py "周杰伦" "Jay Chou" --output artists/jay_chou.yaml
    uv run python create_artist.py "周杰伦" "Jay Chou" --verbose
    uv run python create_artist.py "周杰伦" "Jay Chou" --max-fix 0   # disable auto-fix
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

from artist_profile import ArtistProfile, load_profile
from claude_llm import claude_call

BASE_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


def _build_research_instructions(name_zh: str, name_en: str) -> str:
    """Return research steps + quality checklist text shared by all modes."""
    return f"""RESEARCH STEPS — Follow these in order before generating YAML:

1. Search "{name_zh} 音乐作品列表" on Chinese Wikipedia → extract every album with complete track lists, every OST with the movie/drama/show source name
2. Search "{name_en} discography" on English Wikipedia → cross-reference album lists, find any missing albums or tracks
3. Search "{name_zh} 演唱会" → extract concert tours with years, aliases, and venue cities
4. Search "{name_zh}" main Wikipedia page → birth year, labels, awards, social media links, group membership info
5. Search for variety show appearances ("{name_zh} 综艺") → extract show names, networks, and any songs performed on those shows
6. Search for collaborations ("{name_zh} 合唱" or "{name_zh} feat") → for EACH collaborator, find specific collaboration song names
7. Search for notable interviewers ("{name_zh} 专访" or "{name_zh} 采访") → find at least 1-2 specific interviewer names

FIELD-LEVEL QUALITY REQUIREMENTS — Every entry must meet these rules:
- Every ost_singles entry MUST have a non-empty "source" field (the movie, drama, or show name). Only leave source empty for standalone digital singles that truly have no associated film/drama/show.
- Every collaborators entry MUST have at least 1 song in the "songs" list. If you cannot find a specific collaboration song for someone, REMOVE that collaborator entirely.
- variety_show_singles MUST be populated if the artist appeared on singing competition shows (e.g., 歌手/我是歌手, 梦想的声音, 蒙面唱将). List the songs they performed.
- notable_interviewers must have at least 1-2 entries (specific people, not outlets).
- All albums must have COMPLETE track lists — do not abbreviate or omit tracks.
- Do NOT include lyricists, producers, or songwriters as collaborators — only include artists who actually SANG together on a duet/collaboration track.

SELF-CHECK — Before outputting, verify:
□ Every OST has a source filled in (or is genuinely a standalone single)
□ Every collaborator has at least 1 song listed
□ No lyricists/producers mistakenly listed as collaborators
□ Album track lists are complete (cross-check with Wikipedia)
□ notable_interviewers is not empty
□ variety_show_singles is populated if singing show appearances exist"""


def _build_generation_prompt(name_zh: str, name_en: str, hebe_yaml: str) -> str:
    """Build the full generation prompt with research steps and format reference."""
    research = _build_research_instructions(name_zh, name_en)

    return f"""Generate a complete artist.yaml for {name_zh} ({name_en}).

CRITICAL — Thoroughly research this artist on the web before generating.
Do NOT rely solely on model knowledge. Use web search for every section.

{research}

Include ALL of the following sections with comprehensive data:
- artist: names, official_channels, labels, birth_year, genre, awards, social_links
- group: (if applicable, otherwise omit this section entirely)
- discography:
  - solo_albums: ALL albums with COMPLETE track lists
  - ost_singles: movie/drama theme songs (each with source)
  - variety_show_singles: (if applicable — songs performed on variety/competition shows)
  - concerts: all known concert tours with years, aliases, venues
  - group_concerts: (if applicable)
  - variety_shows: TV show appearances
  - collaborators: with specific collaboration songs (singers only, not lyricists)
  - group_mvs: (if applicable)
  - venues: common concert venues
  - interview_channels: media outlets that have interviewed this artist
  - notable_interviewers: specific interviewers (people, not outlets)
  - western_artist_blacklist: common western artists that might appear in search noise
  - other_chinese_artist_blacklist: other Chinese artists to filter out
  - wrong_context_patterns: patterns that indicate wrong search results
- categories: video categories with id, key, label, output_path, description
- classification: priority order for classification rules

Use this as the EXACT format reference (match the structure precisely):

{hebe_yaml}

IMPORTANT:
- Output ONLY valid YAML, no explanations or markdown fences
- Be comprehensive: include ALL known albums with ALL tracks
- Use the same category structure but adapt labels if the artist has no group
- If the artist has no group, omit the 'group' section and group-related categories entirely
- Adjust category IDs accordingly if fewer categories
"""


def _strip_yaml_fences(content: str) -> str:
    """Strip markdown fences if present."""
    content = content.strip()
    if content.startswith("```"):
        first_nl = content.index("\n") if "\n" in content else len(content)
        content = content[first_nl + 1:]
    if content.endswith("```"):
        content = content[:-3].strip()
    return content


def _find_quality_issues(profile: ArtistProfile) -> list[str]:
    """Check for common quality gaps and return human-readable issue descriptions."""
    issues = []

    # OST singles with empty source
    empty_source_osts = [s.name for s in profile.discography.ost_singles if not s.source]
    if empty_source_osts:
        issues.append(
            f"OST singles with empty 'source' field ({len(empty_source_osts)} of "
            f"{len(profile.discography.ost_singles)}): {', '.join(empty_source_osts)}. "
            "Research the movie/drama/show each song is from and fill in the source. "
            "Only leave source empty for standalone digital singles with no associated film/drama."
        )

    # Collaborators with empty songs
    empty_songs_collabs = [c.name for c in profile.discography.collaborators if not c.songs]
    if empty_songs_collabs:
        issues.append(
            f"Collaborators with empty 'songs' list ({len(empty_songs_collabs)} of "
            f"{len(profile.discography.collaborators)}): {', '.join(empty_songs_collabs)}. "
            "For each, research the specific collaboration songs, or REMOVE the collaborator "
            "if no duet/collaboration track exists (e.g., remove lyricists/producers)."
        )

    # Variety show singles empty when singing shows exist
    singing_show_keywords = ["歌手", "我是歌手", "梦想的声音", "蒙面", "好声音", "声入人心",
                             "天赐的声音", "唱将", "音乐", "歌", "singer"]
    has_singing_shows = any(
        any(kw in v.name.lower() for kw in singing_show_keywords)
        for v in profile.discography.variety_shows
    )
    if has_singing_shows and not profile.discography.variety_show_singles:
        show_names = [v.name for v in profile.discography.variety_shows
                      if any(kw in v.name.lower() for kw in singing_show_keywords)]
        issues.append(
            f"variety_show_singles is empty but singing competition shows exist in variety_shows: "
            f"{', '.join(show_names)}. "
            "Research the songs performed on these shows and add them to variety_show_singles."
        )

    # Empty notable_interviewers
    if not profile.discography.notable_interviewers:
        issues.append(
            "notable_interviewers is empty. Research specific people (not outlets) who have "
            f"interviewed {profile.artist.names.primary} and add at least 1-2 entries."
        )

    # Albums with suspiciously few tracks
    short_albums = [
        f"{a.name} ({len(a.tracks)} tracks)"
        for a in profile.discography.solo_albums
        if len(a.tracks) < 3
    ]
    if short_albums:
        issues.append(
            f"Albums with fewer than 3 tracks (likely incomplete): {', '.join(short_albums)}. "
            "Research the complete track lists on Wikipedia."
        )

    return issues


def _validate_and_fix(
    yaml_content: str,
    name_zh: str,
    name_en: str,
    model: str,
    verbose: bool,
    timeout: int,
    max_iterations: int = 2,
) -> str:
    """Parse, validate, and iteratively fix quality issues in generated YAML."""
    best_content = yaml_content

    for iteration in range(max_iterations + 1):  # iteration 0 = initial check
        # Parse and validate
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False, encoding="utf-8"
            ) as f:
                f.write(best_content)
                tmp_path = f.name

            profile = load_profile(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)
        except Exception as e:
            if iteration == 0:
                print(f"Warning: Initial validation failed: {e}")
                print("The YAML will still be saved — please review and fix manually.")
                return best_content
            # Fix iteration produced invalid YAML — return previous version
            print(f"  Fix iteration {iteration} produced invalid YAML, keeping previous version.")
            return best_content

        # Print stats
        prefix = "  " if iteration > 0 else ""
        print(f"{prefix}Validation passed!")
        print(f"{prefix}  Artist: {profile.artist.names.primary} ({profile.artist.names.english})")
        print(f"{prefix}  Albums: {len(profile.discography.solo_albums)}")
        print(f"{prefix}  OST singles: {len(profile.discography.ost_singles)}")
        print(f"{prefix}  Concerts: {len(profile.discography.concerts)}")
        print(f"{prefix}  Collaborators: {len(profile.discography.collaborators)}")
        print(f"{prefix}  Categories: {len(profile.categories)}")

        # Check quality
        issues = _find_quality_issues(profile)
        if not issues:
            if iteration > 0:
                print(f"  All quality issues resolved after {iteration} fix iteration(s).")
            else:
                print("No quality issues found.")
            return best_content

        print(f"\n{'  ' if iteration > 0 else ''}Found {len(issues)} quality issue(s):")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")

        # If no more fix iterations, return what we have
        if iteration >= max_iterations:
            print(f"\nMax fix iterations ({max_iterations}) reached. Saving current version.")
            return best_content

        # Call Claude to fix
        print(f"\nRunning auto-fix iteration {iteration + 1}/{max_iterations}...")
        fix_prompt = f"""Fix the following quality issues in this artist YAML for {name_zh} ({name_en}).

ISSUES TO FIX:
{chr(10).join(f"- {issue}" for issue in issues)}

CURRENT YAML:
{best_content}

INSTRUCTIONS:
- Research the web to find the missing information
- Output the COMPLETE corrected YAML (not just the changed parts)
- Output ONLY valid YAML, no explanations or markdown fences
- Keep all existing correct data intact — only fix the listed issues
"""
        try:
            fixed = claude_call(
                prompt=fix_prompt,
                model=model,
                needs_tools=True,
                timeout=timeout,
                verbose=verbose,
            )
            fixed = _strip_yaml_fences(fixed)
            if fixed:
                best_content = fixed
        except Exception as e:
            print(f"  Auto-fix call failed: {e}")
            return best_content

    return best_content


def _run_live(name_zh: str, name_en: str, model: str, output_path: Path) -> None:
    """Launch an interactive Claude Code session that the user can watch and interact with."""
    research = _build_research_instructions(name_zh, name_en)

    prompt = f"""請參考 artists/hebe.yaml 的格式，為「{name_zh}」({name_en}) 生成完整的 artist.yaml。

要求：
- 先讀取 artists/hebe.yaml 了解完整結構和所有欄位
- 包含：所有專輯及完整曲目、OST、演唱會、綜藝、合作者、官方頻道、黑名單等
- 如果沒有團體，省略 group 相關部分和 group_mv 類別
- 將結果寫入 {output_path}

{research}

完成寫入後，請驗證結果：
- 執行 `from artist_profile import load_profile; p = load_profile('{output_path}')` 確認 schema 正確
- 檢查上述品質要求是否都滿足
"""

    print(f"Starting interactive Claude Code session...")
    print(f"Claude will read hebe.yaml, research {name_zh}, and write {output_path}")
    print(f"You can interact with Claude during the process.")
    print()

    cmd = ["claude", prompt, "--model", model, "--dangerously-skip-permissions"]
    proc = subprocess.Popen(cmd)
    proc.wait()

    # Post-validation
    print()
    if output_path.exists():
        try:
            profile = load_profile(str(output_path))
            print(f"Validation passed!")
            print(f"  Artist: {profile.artist.names.primary} ({profile.artist.names.english})")
            print(f"  Albums: {len(profile.discography.solo_albums)}")
            print(f"  OST singles: {len(profile.discography.ost_singles)}")
            print(f"  Concerts: {len(profile.discography.concerts)}")
            print(f"  Categories: {len(profile.categories)}")

            issues = _find_quality_issues(profile)
            if issues:
                print(f"\nQuality issues found ({len(issues)}):")
                for i, issue in enumerate(issues, 1):
                    print(f"  {i}. {issue}")
                print("\nConsider re-running with --max-fix to auto-fix these.")
        except Exception as e:
            print(f"Warning: Validation failed: {e}")
            print("Please review and fix the generated YAML manually.")
    else:
        print(f"Warning: {output_path} not found. Claude may not have written the file.")


def main():
    parser = argparse.ArgumentParser(description="Generate artist YAML for a new artist")
    parser.add_argument("name_zh", help="Artist name in Chinese (e.g., 周杰伦)")
    parser.add_argument("name_en", help="Artist name in English (e.g., Jay Chou)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output path (default: artists/{slug}.yaml)")
    parser.add_argument("--model", type=str, default="opus",
                        help="Claude model to use (default: opus)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show claude CLI progress in real time")
    parser.add_argument("--live", action="store_true",
                        help="Open interactive Claude Code session (watch Claude work)")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Timeout in seconds per Claude call (default: 600)")
    parser.add_argument("--max-fix", type=int, default=2,
                        help="Max auto-fix iterations (default: 2, set 0 to disable)")
    args = parser.parse_args()

    # Set up logging for claude_llm
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        slug = args.name_en.lower().replace(" ", "_").replace(".", "")
        output_path = BASE_DIR / "artists" / f"{slug}.yaml"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating artist YAML for {args.name_zh} ({args.name_en})...")
    print(f"Model: {args.model}")
    print(f"Output: {output_path}")
    print()

    # --live: interactive Claude Code session (no need to embed hebe.yaml in prompt)
    if args.live:
        _run_live(args.name_zh, args.name_en, args.model, output_path)
        return

    # Load hebe.yaml as format reference for non-interactive modes
    hebe_path = BASE_DIR / "artists" / "hebe.yaml"
    if not hebe_path.exists():
        print(f"Error: Reference YAML not found at {hebe_path}")
        sys.exit(1)

    hebe_yaml = hebe_path.read_text(encoding="utf-8")
    prompt = _build_generation_prompt(args.name_zh, args.name_en, hebe_yaml)

    print("Calling Claude for initial generation...")
    try:
        content = claude_call(
            prompt=prompt,
            model=args.model,
            needs_tools=True,
            timeout=args.timeout,
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"Error: Claude CLI failed: {e}")
        sys.exit(1)

    content = _strip_yaml_fences(content)

    # Validate and auto-fix
    content = _validate_and_fix(
        yaml_content=content,
        name_zh=args.name_zh,
        name_en=args.name_en,
        model=args.model,
        verbose=args.verbose,
        timeout=args.timeout,
        max_iterations=args.max_fix,
    )

    # Write output
    output_path.write_text(content, encoding="utf-8")
    print(f"\nSaved to: {output_path}")
    print("Please review the generated YAML and adjust as needed.")


if __name__ == "__main__":
    main()
