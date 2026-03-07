"""
classify.py — Phase 3: Waterfall rules + LLM batch classification.

1. Apply exclusion filter (strong exclusion terms)
2. Run waterfall rule engine (categories.yaml priority order)
3. Batch unmatched items to LLM (Gemini Flash via LiteLLM)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import yaml

from agent.utils import normalize_title, parse_duration_to_seconds

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")

VALID_CATEGORIES = {"personalMV", "singles", "concerts", "variety", "interviews", "sheMV", "collabs", "exclude"}

LLM_BATCH_SIZE = 50


def _load_config() -> tuple[dict, dict]:
    """Load artist.yaml and categories.yaml."""
    with open(os.path.join(CONFIG_DIR, "artist.yaml"), "r", encoding="utf-8") as f:
        artist = yaml.safe_load(f)
    with open(os.path.join(CONFIG_DIR, "categories.yaml"), "r", encoding="utf-8") as f:
        categories = yaml.safe_load(f)
    return artist, categories


def _get_official_channel_names(artist: dict) -> set[str]:
    """Collect all official channel names (lowercased)."""
    names = set()
    for platform_channels in artist.get("official_channels", {}).values():
        for ch in platform_channels:
            if isinstance(ch, dict):
                names.add(ch["name"].lower())
            else:
                names.add(str(ch).lower())
    return names


def _get_media_partner_names(artist: dict) -> set[str]:
    """Collect media partner channel names (lowercased)."""
    return {name.lower() for name in artist.get("media_partner_channels", [])}


def _get_collaborator_names(artist: dict) -> list[str]:
    """Get all collaborator names."""
    return artist.get("collaborators", [])


def _apply_exclusion(items: list[dict], artist: dict) -> tuple[list[dict], list[dict]]:
    """Filter out items matching strong exclusion terms.

    Returns (kept, excluded).
    """
    exclusion_terms = [t.lower() for t in artist.get("exclusion_terms", {}).get("strong", [])]
    kept = []
    excluded = []

    for item in items:
        title = (item.get("title") or "").lower()
        if any(term in title for term in exclusion_terms):
            item["category"] = "exclude"
            item["classify_method"] = "rule"
            item["classify_rule"] = "exclusion_filter"
            excluded.append(item)
        else:
            kept.append(item)

    logger.info("Exclusion filter: %d excluded, %d kept", len(excluded), len(kept))
    return kept, excluded


def _check_condition(item: dict, condition_key: str, condition_value,
                     official_channels: set[str], partner_channels: set[str],
                     collaborators: list[str]) -> bool:
    """Check a single rule condition against an item."""
    title = item.get("title", "")
    title_lower = title.lower()
    channel = (item.get("channel") or item.get("author") or "").lower()
    dur = item.get("duration_seconds", 0) or parse_duration_to_seconds(item.get("duration", ""))

    if condition_key == "channel_is_official":
        return any(name in channel for name in official_channels) == condition_value

    if condition_key == "channel_is_media_partner":
        return any(name in channel for name in partner_channels) == condition_value

    if condition_key in ("title_contains_any", "title_contains_any_2"):
        return any(kw.lower() in title_lower for kw in condition_value)

    if condition_key == "title_not_contains_any":
        return not any(kw.lower() in title_lower for kw in condition_value)

    if condition_key == "min_duration_seconds":
        return dur >= condition_value

    if condition_key == "max_duration_seconds":
        return dur == 0 or dur <= condition_value  # 0 means unknown, don't reject

    if condition_key == "title_contains_collaborator":
        nt = normalize_title(title)
        return any(normalize_title(name) in nt for name in collaborators)

    logger.warning("Unknown condition: %s", condition_key)
    return True


def _apply_rules(items: list[dict], categories_config: dict, artist: dict) -> tuple[list[dict], list[dict]]:
    """Apply waterfall rule engine. First match wins.

    Returns (classified, unmatched).
    """
    official_channels = _get_official_channel_names(artist)
    partner_channels = _get_media_partner_names(artist)
    collaborators = _get_collaborator_names(artist)

    category_defs = categories_config.get("categories", [])
    classified = []
    unmatched = []

    for item in items:
        matched = False
        for cat_def in category_defs:
            cat_name = cat_def["name"]
            for rule in cat_def.get("rules", []):
                conditions = rule.get("conditions", {})
                if all(
                    _check_condition(item, k, v, official_channels, partner_channels, collaborators)
                    for k, v in conditions.items()
                ):
                    item["category"] = cat_name
                    item["classify_method"] = "rule"
                    item["classify_rule"] = rule["id"]
                    classified.append(item)
                    matched = True
                    break
            if matched:
                break

        if not matched:
            unmatched.append(item)

    logger.info("Rule engine: %d classified, %d unmatched", len(classified), len(unmatched))
    return classified, unmatched


def _classify_with_llm(items: list[dict]) -> list[dict]:
    """Batch-classify unmatched items using LLM (Gemini Flash via LiteLLM)."""
    if not items:
        return []

    try:
        import litellm
    except ImportError:
        logger.warning("litellm not available, assigning unmatched to 'singles'")
        for item in items:
            item["category"] = "singles"
            item["classify_method"] = "fallback"
            item["classify_rule"] = "no_llm_available"
        return items

    from dotenv import load_dotenv
    agent_env = os.path.join(os.path.dirname(__file__), ".env")
    collector_env = os.path.join(os.path.dirname(__file__), "..", "collector", ".env")
    load_dotenv(agent_env if os.path.exists(agent_env) else collector_env)

    classified = []

    for batch_start in range(0, len(items), LLM_BATCH_SIZE):
        batch = items[batch_start:batch_start + LLM_BATCH_SIZE]

        # Build prompt
        items_text = ""
        for i, item in enumerate(batch):
            items_text += (
                f"\n{i+1}. Title: {item.get('title', 'N/A')}\n"
                f"   Channel: {item.get('channel') or item.get('author', 'N/A')}\n"
                f"   Duration: {item.get('duration', 'N/A')}\n"
                f"   Source: {item.get('source', 'N/A')}\n"
                f"   Description: {(item.get('description') or item.get('snippet', ''))[:100]}\n"
            )

        prompt = f"""Classify each video about Taiwanese singer Hebe Tien (田馥甄) into exactly ONE category.

Categories:
- personalMV: Official music videos for her solo songs
- singles: OST songs, digital singles, non-album tracks
- concerts: Concert recordings, live performances at concerts
- variety: TV show appearances, award show performances, variety shows
- interviews: Interviews, press conferences
- sheMV: S.H.E group music videos
- collabs: Collaborations/duets with other artists
- exclude: Not related to Hebe Tien / covers / karaoke / tutorials

Videos to classify:
{items_text}

Respond with ONLY a JSON array of category strings, one per video, in order.
Example: ["personalMV", "concerts", "variety"]
"""

        try:
            response = litellm.completion(
                model="openrouter/google/gemini-2.5-flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )
            content = response.choices[0].message.content.strip()

            # Parse JSON from response (handle markdown code blocks)
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            categories_result = json.loads(content)

            for i, item in enumerate(batch):
                if i < len(categories_result):
                    cat = categories_result[i]
                    if cat in VALID_CATEGORIES:
                        item["category"] = cat
                    else:
                        item["category"] = "singles"  # fallback
                else:
                    item["category"] = "singles"
                item["classify_method"] = "llm"
                item["classify_rule"] = "gemini_flash"
                classified.append(item)

            logger.info("LLM batch %d-%d: classified %d items",
                        batch_start, batch_start + len(batch), len(batch))

        except Exception as e:
            logger.error("LLM classification failed: %s", e)
            for item in batch:
                item["category"] = "singles"
                item["classify_method"] = "fallback"
                item["classify_rule"] = f"llm_error:{str(e)[:50]}"
                classified.append(item)

    return classified


def run_classify(deduped_path: str | None = None) -> str:
    """Execute Phase 3: classify all items.

    Returns path to the output file.
    """
    if deduped_path is None:
        deduped_path = os.path.join(DATA_DIR, "deduped.json")

    with open(deduped_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["results"]
    logger.info("Phase 3 (classify): starting with %d items", len(items))

    artist, categories_config = _load_config()

    # Step 1: Exclusion filter
    kept, excluded = _apply_exclusion(items, artist)

    # Step 2: Waterfall rules
    classified, unmatched = _apply_rules(kept, categories_config, artist)

    # Step 3: LLM for unmatched
    llm_classified = _classify_with_llm(unmatched)

    # Combine all
    all_items = classified + llm_classified + excluded

    # Stats
    stats: dict[str, int] = {}
    method_stats: dict[str, int] = {"rule": 0, "llm": 0, "fallback": 0}
    for item in all_items:
        cat = item.get("category", "unknown")
        stats[cat] = stats.get(cat, 0) + 1
        method = item.get("classify_method", "unknown")
        method_stats[method] = method_stats.get(method, 0) + 1

    logger.info("Classification stats: %s", stats)
    logger.info("Method breakdown: %s", method_stats)

    # Save
    output_path = os.path.join(DATA_DIR, "classified.json")
    output = {
        "phase": "classify",
        "created_at": datetime.now().isoformat(),
        "total_items": len(all_items),
        "category_stats": stats,
        "method_stats": method_stats,
        "results": all_items,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("Phase 3 complete: %d items classified -> %s", len(all_items), output_path)
    return output_path
