"""
test_generate.py — Tests for generate.py.

Covers:
- CLI argument parsing
- step_create_yaml: skipping existing, calling create_artist
- step_pipeline: phase routing, verbose flag
- step_reclassify: subprocess invocation
- step_web_build: pnpm availability, install/build flow
- print_summary: output formatting with/without data
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from generate import (
    step_create_yaml,
    step_reclassify,
    step_web_build,
    print_summary,
    main,
)


# ---------------------------------------------------------------------------
# step_create_yaml
# ---------------------------------------------------------------------------

class TestStepCreateYaml:
    def test_existing_yaml_skips_creation(self, tmp_path):
        """If YAML already exists, returns path without calling create_artist."""
        yaml_path = tmp_path / "artists" / "test_artist.yaml"
        yaml_path.parent.mkdir(parents=True)
        yaml_path.write_text("artist: test", encoding="utf-8")

        with patch("generate.BASE_DIR", tmp_path):
            result = step_create_yaml("测试", "Test Artist", "opus", False)
        assert result == yaml_path

    def test_slug_generation(self, tmp_path):
        """Slug is derived from English name correctly."""
        with patch("generate.BASE_DIR", tmp_path), \
             patch("create_artist.main") as mock_create:
            yaml_path = tmp_path / "artists" / "jay_chou.yaml"
            yaml_path.parent.mkdir(parents=True)

            def fake_create():
                yaml_path.write_text("artist: test")

            mock_create.side_effect = fake_create
            result = step_create_yaml("周杰伦", "Jay Chou", "opus", False)
            assert result.name == "jay_chou.yaml"

    def test_dots_removed_from_slug(self, tmp_path):
        """Dots are stripped from the slug."""
        with patch("generate.BASE_DIR", tmp_path), \
             patch("create_artist.main") as mock_create:
            yaml_path = tmp_path / "artists" / "jj_lin.yaml"
            yaml_path.parent.mkdir(parents=True)

            def fake_create():
                yaml_path.write_text("artist: test")

            mock_create.side_effect = fake_create
            result = step_create_yaml("林俊杰", "J.J. Lin", "opus", False)
            assert result.name == "jj_lin.yaml"


# ---------------------------------------------------------------------------
# step_reclassify
# ---------------------------------------------------------------------------

class TestStepReclassify:
    @patch("generate.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="Reclassified 10 items\n", stderr="", returncode=0,
        )
        step_reclassify(Path("artists/test.yaml"), no_llm=False)
        cmd = mock_run.call_args[0][0]
        assert "--apply" in cmd
        assert "reclassify.py" in cmd[1]

    @patch("generate.subprocess.run")
    def test_no_llm_flag(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="", stderr="", returncode=0,
        )
        step_reclassify(Path("artists/test.yaml"), no_llm=True)
        cmd = mock_run.call_args[0][0]
        assert "--no-llm" in cmd

    @patch("generate.subprocess.run")
    def test_failure_exits(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="", stderr="error", returncode=1,
        )
        with pytest.raises(SystemExit):
            step_reclassify(Path("artists/test.yaml"), no_llm=False)


# ---------------------------------------------------------------------------
# step_web_build
# ---------------------------------------------------------------------------

class TestStepWebBuild:
    @patch("generate.subprocess.run")
    def test_pnpm_not_found_exits(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        with patch("generate.WEB_DIR", Path("/fake/web")), \
             patch.object(Path, "exists", return_value=True):
            with pytest.raises(SystemExit):
                step_web_build()

    @patch("generate.subprocess.run")
    def test_install_failure_exits(self, mock_run):
        pnpm_check = MagicMock(returncode=0)
        install_fail = MagicMock(stdout="", stderr="install error", returncode=1)
        mock_run.side_effect = [pnpm_check, install_fail]

        with patch("generate.WEB_DIR", Path("/fake/web")), \
             patch.object(Path, "exists", return_value=True):
            with pytest.raises(SystemExit):
                step_web_build()

    @patch("generate.subprocess.run")
    def test_build_failure_exits(self, mock_run):
        pnpm_check = MagicMock(returncode=0)
        install_ok = MagicMock(stdout="", stderr="", returncode=0)
        build_fail = MagicMock(stdout="", stderr="build error", returncode=1)
        mock_run.side_effect = [pnpm_check, install_ok, build_fail]

        with patch("generate.WEB_DIR", Path("/fake/web")), \
             patch.object(Path, "exists", return_value=True):
            with pytest.raises(SystemExit):
                step_web_build()

    @patch("generate.subprocess.run")
    def test_success(self, mock_run):
        pnpm_check = MagicMock(returncode=0)
        install_ok = MagicMock(stdout="", stderr="", returncode=0)
        build_ok = MagicMock(stdout="", stderr="", returncode=0)
        mock_run.side_effect = [pnpm_check, install_ok, build_ok]

        with patch("generate.WEB_DIR", Path("/fake/web")), \
             patch.object(Path, "exists", return_value=True):
            step_web_build()  # Should not raise

    def test_missing_web_dir_exits(self):
        with patch("generate.WEB_DIR", Path("/nonexistent/web")):
            with pytest.raises(SystemExit):
                step_web_build()


# ---------------------------------------------------------------------------
# print_summary
# ---------------------------------------------------------------------------

class TestPrintSummary:
    def test_summary_with_data(self, tmp_path, capsys):
        """Prints correct counts from processed files."""
        # Create artist YAML
        artist_yaml = tmp_path / "artists" / "test.yaml"
        artist_yaml.parent.mkdir(parents=True)
        artist_yaml.write_text("""
artist:
  names:
    primary: 测试
    english: Test
    aliases: []
  official_channels: []
  labels: []
discography:
  solo_albums: []
  ost_singles: []
  concerts: []
  variety_shows: []
  collaborators: []
categories:
  - id: 2
    key: mv
    label: MV
  - id: 3
    key: concerts
    label: Concerts
classification:
  priority: []
""", encoding="utf-8")

        # Create processed data
        data_dir = tmp_path / "data" / "test" / "processed"
        data_dir.mkdir(parents=True)
        (data_dir / "file_2.json").write_text(
            json.dumps({"total_results": 15}), encoding="utf-8"
        )
        (data_dir / "file_3.json").write_text(
            json.dumps({"total_results": 8}), encoding="utf-8"
        )

        with patch("generate.BASE_DIR", tmp_path):
            print_summary(artist_yaml)

        captured = capsys.readouterr()
        assert "23 videos" in captured.out
        assert "2 categories" in captured.out

    def test_summary_no_data(self, tmp_path, capsys):
        """Handles missing processed directory gracefully."""
        artist_yaml = tmp_path / "artists" / "test.yaml"
        artist_yaml.parent.mkdir(parents=True)
        artist_yaml.write_text("""
artist:
  names:
    primary: 测试
    english: Test
    aliases: []
  official_channels: []
  labels: []
discography:
  solo_albums: []
  ost_singles: []
  concerts: []
  variety_shows: []
  collaborators: []
categories:
  - id: 2
    key: mv
    label: MV
classification:
  priority: []
""", encoding="utf-8")

        with patch("generate.BASE_DIR", tmp_path):
            print_summary(artist_yaml)

        captured = capsys.readouterr()
        assert "0 videos" in captured.out


# ---------------------------------------------------------------------------
# main — CLI argument validation
# ---------------------------------------------------------------------------

class TestMainArgParsing:
    def test_missing_both_names_and_artist_flag(self):
        """Must provide either names or --artist."""
        with patch("sys.argv", ["generate.py"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse error

    def test_missing_english_name(self):
        """Must provide both zh and en names."""
        with patch("sys.argv", ["generate.py", "周杰伦"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2

    def test_nonexistent_artist_yaml(self):
        with patch("sys.argv", ["generate.py", "--artist", "/nonexistent.yaml"]):
            with pytest.raises(SystemExit):
                main()

    @patch("generate.print_summary")
    @patch("generate.step_pipeline")
    @patch("generate.step_create_yaml")
    def test_full_flow_with_names(self, mock_create, mock_pipeline, mock_summary):
        mock_create.return_value = Path("artists/test.yaml")
        with patch("sys.argv", ["generate.py", "测试", "Test", "--skip-build"]):
            main()
        mock_create.assert_called_once()
        mock_pipeline.assert_called_once()

    @patch("generate.print_summary")
    @patch("generate.step_pipeline")
    def test_artist_flag_skips_create(self, mock_pipeline, mock_summary, tmp_path):
        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text("""
artist:
  names:
    primary: 测试
    english: Test
    aliases: []
  official_channels: []
  labels: []
discography:
  solo_albums: []
  ost_singles: []
  concerts: []
  variety_shows: []
  collaborators: []
categories: []
classification:
  priority: []
""")
        with patch("sys.argv", ["generate.py", "--artist", str(yaml_path), "--skip-build"]):
            main()
        mock_pipeline.assert_called_once()

    @patch("generate.print_summary")
    @patch("generate.step_pipeline")
    @patch("generate.step_create_yaml")
    def test_phase_flag_passed_through(self, mock_create, mock_pipeline, mock_summary):
        mock_create.return_value = Path("artists/test.yaml")
        with patch("sys.argv", ["generate.py", "测试", "Test", "--phase", "1", "--skip-build"]):
            main()
        _, kwargs = mock_pipeline.call_args
        # phase is a positional arg in step_pipeline call
        args = mock_pipeline.call_args[0]
        assert args[1] == 1  # phase argument
