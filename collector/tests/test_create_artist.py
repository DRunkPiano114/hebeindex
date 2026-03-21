"""
test_create_artist.py — Tests for create_artist.py.

Covers:
- _strip_yaml_fences: markdown fence removal
- _find_quality_issues: quality gap detection for all checked fields
- _build_research_instructions: prompt construction
- _build_generation_prompt: full prompt with YAML reference
- _validate_and_fix: iterative validation and fix loop
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from create_artist import (
    _strip_yaml_fences,
    _find_quality_issues,
    _build_research_instructions,
    _build_generation_prompt,
    _validate_and_fix,
)
from artist_profile import (
    ArtistProfile,
    ArtistInfo,
    ArtistNames,
    GroupInfo,
    Discography,
    Album,
    OSTSingle,
    Concert,
    VarietyShow,
    Collaborator,
    VarietyShowSingle,
    Category,
    ClassificationConfig,
)


# ---------------------------------------------------------------------------
# _strip_yaml_fences
# ---------------------------------------------------------------------------

class TestStripYamlFences:
    def test_no_fences(self):
        assert _strip_yaml_fences("artist:\n  name: test") == "artist:\n  name: test"

    def test_yaml_fences(self):
        content = "```yaml\nartist:\n  name: test\n```"
        assert _strip_yaml_fences(content) == "artist:\n  name: test"

    def test_plain_fences(self):
        content = "```\nartist:\n  name: test\n```"
        assert _strip_yaml_fences(content) == "artist:\n  name: test"

    def test_leading_whitespace_stripped(self):
        content = "  \n```yaml\ncontent\n```  \n"
        assert _strip_yaml_fences(content) == "content"

    def test_only_opening_fence(self):
        content = "```yaml\ncontent here"
        result = _strip_yaml_fences(content)
        assert result == "content here"

    def test_only_closing_fence(self):
        content = "content here\n```"
        result = _strip_yaml_fences(content)
        assert result == "content here"

    def test_empty_string(self):
        assert _strip_yaml_fences("") == ""

    def test_whitespace_only(self):
        assert _strip_yaml_fences("   ") == ""

    def test_multiple_code_blocks_strips_outer(self):
        content = "```yaml\ninner ```\ncontent\n```"
        result = _strip_yaml_fences(content)
        assert "inner ```" in result
        assert not result.startswith("```")

    def test_fences_with_language_tag(self):
        content = "```yml\nartist:\n  name: test\n```"
        result = _strip_yaml_fences(content)
        assert result == "artist:\n  name: test"


# ---------------------------------------------------------------------------
# _find_quality_issues — fixture helpers
# ---------------------------------------------------------------------------

def _make_profile(
    ost_singles=None,
    collaborators=None,
    variety_shows=None,
    variety_show_singles=None,
    notable_interviewers=None,
    solo_albums=None,
) -> ArtistProfile:
    """Build a minimal ArtistProfile for quality issue testing."""
    return ArtistProfile(
        artist=ArtistInfo(
            names=ArtistNames(primary="测试", english="Test", aliases=[]),
            official_channels=[],
            labels=[],
        ),
        discography=Discography(
            solo_albums=solo_albums if solo_albums is not None else [
                Album(name="Album A", year=2020, tracks=["T1", "T2", "T3"]),
            ],
            ost_singles=ost_singles if ost_singles is not None else [],
            variety_show_singles=variety_show_singles if variety_show_singles is not None else [],
            concerts=[],
            variety_shows=variety_shows if variety_shows is not None else [],
            collaborators=collaborators if collaborators is not None else [],
            notable_interviewers=notable_interviewers if notable_interviewers is not None else ["记者A"],
        ),
        categories=[],
        classification=ClassificationConfig(priority=[]),
    )


# ---------------------------------------------------------------------------
# _find_quality_issues
# ---------------------------------------------------------------------------

class TestFindQualityIssues:
    def test_no_issues_with_clean_profile(self):
        profile = _make_profile(
            ost_singles=[OSTSingle(name="OST", source="Movie", year=2020)],
            collaborators=[Collaborator(name="Artist B", songs=["Song X"])],
            notable_interviewers=["Interviewer A"],
        )
        assert _find_quality_issues(profile) == []

    def test_ost_with_empty_source(self):
        profile = _make_profile(
            ost_singles=[
                OSTSingle(name="Good OST", source="Movie A", year=2020),
                OSTSingle(name="Bad OST", source="", year=2021),
            ],
        )
        issues = _find_quality_issues(profile)
        assert len(issues) == 1
        assert "Bad OST" in issues[0]
        assert "source" in issues[0].lower()

    def test_all_osts_have_source_no_issue(self):
        profile = _make_profile(
            ost_singles=[
                OSTSingle(name="O1", source="Film", year=2020),
                OSTSingle(name="O2", source="Drama", year=2021),
            ],
        )
        issues = _find_quality_issues(profile)
        ost_issues = [i for i in issues if "source" in i.lower() and "OST" in i]
        assert len(ost_issues) == 0

    def test_collaborator_with_empty_songs(self):
        profile = _make_profile(
            collaborators=[
                Collaborator(name="Good Collab", songs=["Duet"]),
                Collaborator(name="Bad Collab", songs=[]),
            ],
        )
        issues = _find_quality_issues(profile)
        collab_issues = [i for i in issues if "Bad Collab" in i]
        assert len(collab_issues) == 1

    def test_all_collaborators_have_songs(self):
        profile = _make_profile(
            collaborators=[
                Collaborator(name="A", songs=["S1"]),
                Collaborator(name="B", songs=["S2", "S3"]),
            ],
        )
        issues = _find_quality_issues(profile)
        collab_issues = [i for i in issues if "collaborator" in i.lower() or "songs" in i.lower()]
        assert len(collab_issues) == 0

    def test_variety_show_singles_empty_with_singing_shows(self):
        profile = _make_profile(
            variety_shows=[
                VarietyShow(name="歌手2024", network="湖南卫视"),
            ],
            variety_show_singles=[],
        )
        issues = _find_quality_issues(profile)
        variety_issues = [i for i in issues if "variety_show_singles" in i]
        assert len(variety_issues) == 1

    def test_variety_show_singles_populated_no_issue(self):
        profile = _make_profile(
            variety_shows=[
                VarietyShow(name="歌手2024", network="湖南卫视"),
            ],
            variety_show_singles=[
                VarietyShowSingle(name="Song", source="歌手2024", year=2024),
            ],
        )
        issues = _find_quality_issues(profile)
        variety_issues = [i for i in issues if "variety_show_singles" in i]
        assert len(variety_issues) == 0

    def test_non_singing_variety_show_no_false_positive(self):
        """Non-singing shows should not trigger variety_show_singles warning."""
        profile = _make_profile(
            variety_shows=[
                VarietyShow(name="快乐大本营", network="湖南卫视"),
            ],
            variety_show_singles=[],
        )
        issues = _find_quality_issues(profile)
        variety_issues = [i for i in issues if "variety_show_singles" in i]
        assert len(variety_issues) == 0

    def test_empty_notable_interviewers(self):
        profile = _make_profile(notable_interviewers=[])
        issues = _find_quality_issues(profile)
        interviewer_issues = [i for i in issues if "notable_interviewers" in i]
        assert len(interviewer_issues) == 1

    def test_notable_interviewers_populated(self):
        profile = _make_profile(notable_interviewers=["Person A", "Person B"])
        issues = _find_quality_issues(profile)
        interviewer_issues = [i for i in issues if "notable_interviewers" in i]
        assert len(interviewer_issues) == 0

    def test_album_with_few_tracks(self):
        profile = _make_profile(
            solo_albums=[
                Album(name="Short Album", year=2020, tracks=["Only One"]),
            ],
        )
        issues = _find_quality_issues(profile)
        album_issues = [i for i in issues if "Short Album" in i]
        assert len(album_issues) == 1
        assert "1 tracks" in album_issues[0]

    def test_album_with_enough_tracks(self):
        profile = _make_profile(
            solo_albums=[
                Album(name="Good Album", year=2020, tracks=["A", "B", "C", "D"]),
            ],
        )
        issues = _find_quality_issues(profile)
        album_issues = [i for i in issues if "incomplete" in i.lower()]
        assert len(album_issues) == 0

    def test_album_exactly_3_tracks_no_issue(self):
        profile = _make_profile(
            solo_albums=[
                Album(name="EP", year=2020, tracks=["A", "B", "C"]),
            ],
        )
        issues = _find_quality_issues(profile)
        album_issues = [i for i in issues if "EP" in i and "tracks" in i]
        assert len(album_issues) == 0

    def test_multiple_issues_combined(self):
        profile = _make_profile(
            ost_singles=[OSTSingle(name="No Source", source="", year=2020)],
            collaborators=[Collaborator(name="No Songs", songs=[])],
            notable_interviewers=[],
            solo_albums=[Album(name="Short", year=2020, tracks=["Only"])],
        )
        issues = _find_quality_issues(profile)
        assert len(issues) >= 3  # OST + collab + interviewers + short album


# ---------------------------------------------------------------------------
# _build_research_instructions
# ---------------------------------------------------------------------------

class TestBuildResearchInstructions:
    def test_contains_artist_names(self):
        text = _build_research_instructions("周杰伦", "Jay Chou")
        assert "周杰伦" in text
        assert "Jay Chou" in text

    def test_contains_research_steps(self):
        text = _build_research_instructions("田馥甄", "Hebe Tien")
        assert "Wikipedia" in text
        assert "discography" in text
        assert "演唱会" in text

    def test_contains_quality_requirements(self):
        text = _build_research_instructions("田馥甄", "Hebe Tien")
        assert "source" in text.lower()
        assert "collaborator" in text.lower()
        assert "SELF-CHECK" in text


# ---------------------------------------------------------------------------
# _build_generation_prompt
# ---------------------------------------------------------------------------

class TestBuildGenerationPrompt:
    def test_contains_artist_name(self):
        prompt = _build_generation_prompt("陈奕迅", "Eason Chan", "sample: yaml")
        assert "陈奕迅" in prompt
        assert "Eason Chan" in prompt

    def test_contains_reference_yaml(self):
        ref_yaml = "artist:\n  names:\n    primary: 田馥甄"
        prompt = _build_generation_prompt("陈奕迅", "Eason Chan", ref_yaml)
        assert ref_yaml in prompt

    def test_contains_section_requirements(self):
        prompt = _build_generation_prompt("陈奕迅", "Eason Chan", "yaml")
        assert "solo_albums" in prompt
        assert "ost_singles" in prompt
        assert "concerts" in prompt
        assert "categories" in prompt
        assert "classification" in prompt

    def test_output_only_yaml_instruction(self):
        prompt = _build_generation_prompt("陈奕迅", "Eason Chan", "yaml")
        assert "ONLY valid YAML" in prompt


# ---------------------------------------------------------------------------
# _validate_and_fix
# ---------------------------------------------------------------------------

class TestValidateAndFix:
    def _make_valid_yaml(self, notable_interviewers=None):
        """Generate valid YAML content for testing."""
        interviewers = notable_interviewers if notable_interviewers is not None else ["Reporter A"]
        if interviewers:
            interviewers_yaml = "\n".join(f"    - {i}" for i in interviewers)
            interviewers_section = f"  notable_interviewers:\n{interviewers_yaml}"
        else:
            interviewers_section = "  notable_interviewers: []"
        return f"""artist:
  names:
    primary: 测试
    english: Test
    aliases: []
  official_channels: []
  labels: []
discography:
  solo_albums:
    - name: Album A
      year: 2020
      tracks:
        - Track 1
        - Track 2
        - Track 3
  ost_singles:
    - name: OST A
      source: Movie A
      year: 2020
  concerts: []
  variety_shows: []
  collaborators:
    - name: Collab A
      songs:
        - Song X
{interviewers_section}
categories: []
classification:
  priority: []
"""

    def test_valid_yaml_returns_unchanged(self):
        yaml_content = self._make_valid_yaml()
        result = _validate_and_fix(
            yaml_content, "测试", "Test", "sonnet", False, 60, max_iterations=0,
        )
        assert result == yaml_content

    def test_invalid_yaml_returns_original(self):
        """Invalid YAML on first parse returns the original content."""
        bad_yaml = "not: valid: yaml: [[[unclosed"
        result = _validate_and_fix(
            bad_yaml, "测试", "Test", "sonnet", False, 60, max_iterations=0,
        )
        assert result == bad_yaml

    @patch("create_artist.claude_call")
    def test_fix_iteration_called_on_issues(self, mock_call):
        """When quality issues exist and max_iterations > 0, claude_call is invoked."""
        yaml_with_issues = self._make_valid_yaml(notable_interviewers=[])
        fixed_yaml = self._make_valid_yaml(notable_interviewers=["Fixed Reporter"])
        mock_call.return_value = fixed_yaml

        result = _validate_and_fix(
            yaml_with_issues, "测试", "Test", "sonnet", False, 60, max_iterations=1,
        )
        mock_call.assert_called_once()
        assert "Fixed Reporter" in result

    @patch("create_artist.claude_call")
    def test_fix_failure_returns_previous(self, mock_call):
        """If fix call produces invalid YAML, returns the previous valid version."""
        yaml_with_issues = self._make_valid_yaml(notable_interviewers=[])
        mock_call.return_value = "totally broken yaml {{{"

        result = _validate_and_fix(
            yaml_with_issues, "测试", "Test", "sonnet", False, 60, max_iterations=1,
        )
        # Should return the original (issues version) since fix was worse
        assert "测试" in result

    @patch("create_artist.claude_call")
    def test_max_iterations_zero_skips_fix(self, mock_call):
        yaml_with_issues = self._make_valid_yaml(notable_interviewers=[])
        result = _validate_and_fix(
            yaml_with_issues, "测试", "Test", "sonnet", False, 60, max_iterations=0,
        )
        mock_call.assert_not_called()
        assert result == yaml_with_issues

    @patch("create_artist.claude_call")
    def test_fix_call_exception_returns_current(self, mock_call):
        """Exception during fix returns the current best content."""
        yaml_with_issues = self._make_valid_yaml(notable_interviewers=[])
        mock_call.side_effect = RuntimeError("API error")

        result = _validate_and_fix(
            yaml_with_issues, "测试", "Test", "sonnet", False, 60, max_iterations=1,
        )
        assert result == yaml_with_issues
