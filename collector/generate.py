#!/usr/bin/env python3
"""
generate.py — Full artist addition flow in one command.

Chains: create YAML -> pipeline phases 1-2 -> phase 3 -> web build -> summary.

Usage:
    uv run python generate.py "周杰伦" "Jay Chou"                      # full flow
    uv run python generate.py "周杰伦" "Jay Chou" --skip-build         # skip web build
    uv run python generate.py --artist artists/jay_chou.yaml            # use existing YAML
    uv run python generate.py --artist artists/jay_chou.yaml --phase 1  # only search
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
WEB_DIR = BASE_DIR.parent / "web"


def _step(label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}\n")


def _fail(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def step_create_yaml(name_zh: str, name_en: str, model: str, verbose: bool) -> Path:
    """Create artist YAML if it doesn't exist. Returns the YAML path."""
    slug = name_en.lower().replace(" ", "_").replace(".", "")
    yaml_path = BASE_DIR / "artists" / f"{slug}.yaml"

    if yaml_path.exists():
        print(f"Artist YAML already exists: {yaml_path}")
        print("Skipping creation, using existing file.")
        return yaml_path

    _step(f"Step 1: Create artist YAML for {name_zh} ({name_en})")

    from create_artist import main as create_main

    # Build sys.argv for create_artist.main()
    orig_argv = sys.argv
    sys.argv = [
        "create_artist.py",
        name_zh,
        name_en,
        "--output", str(yaml_path),
        "--model", model,
    ]
    if verbose:
        sys.argv.append("--verbose")

    try:
        create_main()
    except SystemExit as e:
        if e.code and e.code != 0:
            _fail(f"Artist YAML creation failed (exit {e.code})")
    finally:
        sys.argv = orig_argv

    if not yaml_path.exists():
        _fail(f"Artist YAML was not created at {yaml_path}")

    return yaml_path


def step_pipeline(artist_path: Path, phase: int | None, no_llm: bool, verbose: bool) -> None:
    """Run pipeline phases. If phase is None, runs 1-2 then 3 separately."""
    from artist_profile import load_profile
    from query_generator import build_search_plan
    from pipeline import phase1_search, phase2_process, phase3_format

    profile = load_profile(str(artist_path))
    search_plan = build_search_plan(profile)
    name = f"{profile.artist.names.primary} ({profile.artist.names.english})"

    print(f"Artist: {name}")
    print(f"Categories: {len(profile.categories)}")
    print(f"Total queries: {sum(len(s['searches']) for s in search_plan)}")

    if verbose:
        import claude_llm
        claude_llm.VERBOSE = True

    if phase is not None:
        # Single phase mode
        if phase == 1:
            _step(f"Pipeline Phase 1: Search ({name})")
            phase1_search(profile, search_plan)
        elif phase == 2:
            _step(f"Pipeline Phase 2: Dedup + Verify ({name})")
            phase2_process(profile, search_plan)
        elif phase == 3:
            _step(f"Pipeline Phase 3: Format ({name})")
            phase3_format(profile, search_plan, use_llm=not no_llm)
        return

    # Full run: phases 1-2 then 3
    _step(f"Step 2: Pipeline Phase 1 — Search ({name})")
    phase1_search(profile, search_plan)

    _step(f"Step 2: Pipeline Phase 2 — Dedup + Verify ({name})")
    phase2_process(profile, search_plan)

    _step(f"Step 3: Pipeline Phase 3 — Format ({name})")
    phase3_format(profile, search_plan, use_llm=not no_llm)


def step_web_build() -> None:
    """Build the web site with pnpm."""
    _step("Step 4: Build web site")

    if not WEB_DIR.exists():
        _fail(f"Web directory not found: {WEB_DIR}")

    # Check pnpm is available
    try:
        subprocess.run(
            ["pnpm", "--version"],
            capture_output=True, check=True,
        )
    except FileNotFoundError:
        _fail("pnpm not found. Install it first: https://pnpm.io/installation")

    # Install dependencies
    print("Installing web dependencies...")
    result = subprocess.run(
        ["pnpm", "install"],
        cwd=WEB_DIR,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        _fail("pnpm install failed")

    # Build
    print("Building web site...")
    result = subprocess.run(
        ["pnpm", "run", "build"],
        cwd=WEB_DIR,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        _fail("pnpm run build failed")

    print(f"Web build complete: {WEB_DIR / 'dist'}")


def print_summary(artist_path: Path) -> None:
    """Print final summary with video counts."""
    from artist_profile import load_profile

    profile = load_profile(str(artist_path))
    name = f"{profile.artist.names.primary} ({profile.artist.names.english})"
    data_dir = BASE_DIR / "data" / profile.slug() / "processed"

    total_videos = 0
    category_count = 0

    for cat in profile.categories:
        proc_path = data_dir / f"file_{cat.id}.json"
        if proc_path.exists():
            data = json.loads(proc_path.read_text("utf-8"))
            count = data.get("total_results", 0)
            if count > 0:
                total_videos += count
                category_count += 1

    print(f"\n{'=' * 60}")
    print(f"  Added {name}: {total_videos} videos across {category_count} categories")
    print(f"{'=' * 60}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Full artist addition flow: YAML -> pipeline -> web build"
    )

    # Artist identification (either names or --artist path)
    parser.add_argument(
        "name_zh", nargs="?", default=None,
        help="Artist name in Chinese (e.g., 周杰伦)",
    )
    parser.add_argument(
        "name_en", nargs="?", default=None,
        help="Artist name in English (e.g., Jay Chou)",
    )
    parser.add_argument(
        "--artist", type=str, default=None,
        help="Path to existing artist YAML (skip creation step)",
    )

    # Pipeline control
    parser.add_argument(
        "--phase", type=int, choices=[1, 2, 3], default=None,
        help="Run only a specific pipeline phase",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Use template fallback instead of LLM for formatting",
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Skip the web site build step",
    )

    # YAML generation options
    parser.add_argument(
        "--model", type=str, default="opus",
        help="Claude model for YAML generation (default: opus)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show detailed progress for LLM calls",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.artist is None and (args.name_zh is None or args.name_en is None):
        parser.error("Provide both name_zh and name_en, or use --artist path")

    if args.artist and not Path(args.artist).exists():
        _fail(f"Artist YAML not found: {args.artist}")

    start = time.time()

    # Step 1: Get or create artist YAML
    if args.artist:
        artist_path = Path(args.artist)
        print(f"Using existing artist YAML: {artist_path}")
    else:
        artist_path = step_create_yaml(
            args.name_zh, args.name_en, args.model, args.verbose,
        )

    # Step 2-3: Run pipeline
    try:
        step_pipeline(artist_path, args.phase, args.no_llm, args.verbose)
    except Exception as exc:
        _fail(f"Pipeline failed: {exc}")

    # Step 4: Build web (skip if --skip-build or running single phase)
    if not args.skip_build and args.phase is None:
        try:
            step_web_build()
        except SystemExit:
            print("\nWeb build failed, but pipeline data is saved.", file=sys.stderr)

    # Summary
    elapsed = time.time() - start
    print_summary(artist_path)
    print(f"  Total time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
