"""Tests for the skills module."""

import os
import tempfile
from pathlib import Path

import pytest

from agent.skills import (
    MAX_COMPATIBILITY_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
    LoadSkillsResult,
    Skill,
    SkillDiagnostic,
    find_skill_md,
    format_skills_for_prompt,
    load_skills,
    load_skills_from_dir,
    parse_frontmatter,
    read_skill,
    validate,
    validate_compatibility,
    validate_description,
    validate_metadata_fields,
    validate_name,
)


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""

    def test_valid_frontmatter(self):
        content = """---
name: test-skill
description: A test skill
---
# Body content
Some instructions here.
"""
        metadata, body = parse_frontmatter(content)
        assert metadata["name"] == "test-skill"
        assert metadata["description"] == "A test skill"
        assert body == "# Body content\nSome instructions here."

    def test_frontmatter_missing(self):
        with pytest.raises(ValueError, match="must start with YAML frontmatter"):
            parse_frontmatter("# No frontmatter")

    def test_frontmatter_not_closed(self):
        # Test that unclosed frontmatter still parses (lenient)
        # This is acceptable behavior - we don't strictly require closing ---
        content = "---name: test---"
        metadata, body = parse_frontmatter(content)
        assert metadata.get("name") == "test"
        assert body == ""

    def test_quoted_strings(self):
        content = """---
name: "quoted-name"
description: 'single quoted'
---
"""
        metadata, _ = parse_frontmatter(content)
        assert metadata["name"] == "quoted-name"
        assert metadata["description"] == "single quoted"

    def test_optional_fields(self):
        content = """---
name: test-skill
description: A test skill
license: Apache-2.0
compatibility: Requires Python 3.11+
---
"""
        metadata, _ = parse_frontmatter(content)
        assert metadata["name"] == "test-skill"
        assert metadata["license"] == "Apache-2.0"
        assert metadata["compatibility"] == "Requires Python 3.11+"


class TestValidateName:
    """Tests for validate_name function."""

    def test_valid_name(self):
        errors = validate_name("pdf-processing")
        assert errors == []

    def test_name_too_long(self):
        long_name = "a" * (MAX_NAME_LENGTH + 1)
        errors = validate_name(long_name)
        assert any("exceeds" in e for e in errors)

    def test_name_uppercase(self):
        errors = validate_name("PDF-Processing")
        assert any("lowercase" in e for e in errors)

    def test_name_starts_with_hyphen(self):
        errors = validate_name("-pdf")
        assert any("cannot start" in e for e in errors)

    def test_name_ends_with_hyphen(self):
        errors = validate_name("pdf-")
        assert any("cannot start or end" in e for e in errors)

    def test_name_consecutive_hyphens(self):
        errors = validate_name("pdf--processing")
        assert any("consecutive" in e for e in errors)

    def test_name_invalid_chars(self):
        errors = validate_name("pdf_process")
        assert any("invalid characters" in e for e in errors)

    def test_name_empty(self):
        errors = validate_name("")
        assert any("non-empty" in e for e in errors)


class TestValidateDescription:
    """Tests for validate_description function."""

    def test_valid_description(self):
        errors = validate_description("A valid description")
        assert errors == []

    def test_description_too_long(self):
        long_desc = "a" * (MAX_DESCRIPTION_LENGTH + 1)
        errors = validate_description(long_desc)
        assert any("exceeds" in e for e in errors)

    def test_description_empty(self):
        errors = validate_description("")
        assert any("non-empty" in e for e in errors)


class TestValidateCompatibility:
    """Tests for validate_compatibility function."""

    def test_valid_compatibility(self):
        errors = validate_compatibility("Requires Python 3.11+")
        assert errors == []

    def test_compatibility_too_long(self):
        long_comp = "a" * (MAX_COMPATIBILITY_LENGTH + 1)
        errors = validate_compatibility(long_comp)
        assert any("exceeds" in e for e in errors)


class TestValidateMetadataFields:
    """Tests for validate_metadata_fields function."""

    def test_allowed_fields(self):
        metadata = {
            "name": "test",
            "description": "Test skill",
            "license": "Apache-2.0",
            "compatibility": "Python 3.11+",
            "metadata": {"author": "test"},
            "allowed-tools": "Read Bash",
        }
        errors = validate_metadata_fields(metadata)
        assert errors == []

    def test_extra_fields(self):
        metadata = {
            "name": "test",
            "description": "Test skill",
            "unknown-field": "value",
        }
        errors = validate_metadata_fields(metadata)
        assert any("Unexpected fields" in e for e in errors)


class TestFindSkillMd:
    """Tests for find_skill_md function."""

    def test_finds_skill_md_uppercase(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: Test\n---")
        result = find_skill_md(skill_dir)
        assert result is not None
        assert result.name == "SKILL.md"

    def test_finds_skill_md_lowercase(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("---\nname: test-skill\ndescription: Test\n---")
        result = find_skill_md(skill_dir)
        assert result is not None
        assert result.name == "skill.md"

    def test_returns_none_when_missing(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        result = find_skill_md(skill_dir)
        assert result is None


class TestReadSkill:
    """Tests for read_skill function."""

    def test_read_valid_skill(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill for testing
---
# Test Skill
Some instructions here.
""")
        skill, diagnostics = read_skill(skill_dir, "user")
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.description == "A test skill for testing"
        assert skill.source == "user"
        assert skill.base_dir == skill_dir

    def test_read_missing_skill_md(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        skill, diagnostics = read_skill(skill_dir, "user")
        assert skill is None
        assert any("Missing SKILL.md" in d.message for d in diagnostics)

    def test_read_missing_description(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
---
# No description
""")
        skill, diagnostics = read_skill(skill_dir, "user")
        assert skill is None


class TestLoadSkillsFromDir:
    """Tests for load_skills_from_dir function."""

    def test_load_from_empty_dir(self, tmp_path):
        result = load_skills_from_dir(tmp_path, "user")
        assert result.skills == []
        assert result.diagnostics == []

    def test_load_skill_from_subdirectory(self, tmp_path):
        skill_dir = tmp_path / "pdf-tools"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: pdf-tools
description: Work with PDF files
---
# PDF Tools
Use this skill for PDF operations.
""")
        result = load_skills_from_dir(tmp_path, "user")
        assert len(result.skills) == 1
        assert result.skills[0].name == "pdf-tools"


class TestLoadSkills:
    """Tests for load_skills function."""

    def test_load_skills_from_both_directories(self, tmp_path, monkeypatch):
        # Create temporary skill directories
        global_dir = tmp_path / "global_skills" / "pdf-tools"
        global_dir.mkdir(parents=True)
        (global_dir / "SKILL.md").write_text("""---
name: pdf-tools
description: Global PDF skill
---
# Global
""")

        project_dir = tmp_path / ".zac" / "skills" / "data-analysis"
        project_dir.mkdir(parents=True)
        (project_dir / "SKILL.md").write_text("""---
name: data-analysis
description: Project data analysis skill
---
# Project
""")

        # Monkeypatch get_default_skill_dirs
        import agent.skills as skills_module

        monkeypatch.setattr(
            skills_module,
            "get_default_skill_dirs",
            lambda: (global_dir.parent, project_dir.parent),
        )

        # Also need to set cwd for project_dir relative resolution
        monkeypatch.chdir(tmp_path)

        result = load_skills(
            global_dir=global_dir.parent,
            project_dir=project_dir.parent,
            cwd=tmp_path,
        )

        assert len(result.skills) == 2
        names = {s.name for s in result.skills}
        assert "pdf-tools" in names
        assert "data-analysis" in names


class TestFormatSkillsForPrompt:
    """Tests for format_skills_for_prompt function."""

    def test_empty_skills(self):
        result = format_skills_for_prompt([])
        assert result == ""

    def test_skills_formatted(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
# Content
""")
            skill, _ = read_skill(skill_dir, "user")

            result = format_skills_for_prompt([skill])

            assert "<available_skills>" in result
            assert "<name>test-skill</name>" in result
            assert "<description>A test skill</description>" in result
            assert "<location>" in result

    def test_skills_with_disable_model_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "secret-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: secret-skill
description: A secret skill
disable-model-invocation: true
---
# Secret content
""")
            skill, _ = read_skill(skill_dir, "user")

            result = format_skills_for_prompt([skill])

            # Should be empty because skill has disable_model_invocation=True
            assert result == ""


class TestValidate:
    """Tests for validate function."""

    def test_validate_valid_skill(self, tmp_path):
        skill_dir = tmp_path / "valid-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: valid-skill
description: A valid skill
---
# Content
""")
        errors = validate(skill_dir)
        assert errors == []

    def test_validate_missing_skill_md(self, tmp_path):
        skill_dir = tmp_path / "no-skill"
        skill_dir.mkdir()
        errors = validate(skill_dir)
        assert any("SKILL.md" in e and "Missing" in e for e in errors)

    def test_validate_name_mismatch(self, tmp_path):
        skill_dir = tmp_path / "wrong-name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: correct-name
description: Description here
---
""")
        errors = validate(skill_dir)
        assert any("must match" in e for e in errors)
