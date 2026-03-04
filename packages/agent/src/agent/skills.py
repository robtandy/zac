"""Skills module for Zac - implements Agent Skills spec.

Reference: https://agentskills.io/specification

This module provides:
- Skill discovery from global (~/.zac/skills) and project (.zac/skills) directories
- YAML frontmatter parsing
- Validation per Agent Skills spec
- XML prompt generation for system prompt integration
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# Agent Skills spec constants
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500

# Allowed frontmatter fields per spec
ALLOWED_FIELDS = {
    "name",
    "description",
    "license",
    "allowed-tools",
    "metadata",
    "compatibility",
}


@dataclass
class SkillProperties:
    """Properties parsed from a skill's SKILL.md frontmatter.

    Attributes:
        name: Skill name in kebab-case (required)
        description: What the skill does (required)
        license: License for the skill (optional)
        compatibility: Compatibility information (optional)
        allowed_tools: Tool patterns the skill requires (optional, experimental)
        metadata: Key-value pairs for client-specific properties (optional)
    """

    name: str
    description: str
    license: Optional[str] = None
    compatibility: Optional[str] = None
    allowed_tools: Optional[str] = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class Skill:
    """A loaded skill with metadata and file path information."""

    name: str
    description: str
    file_path: Path
    base_dir: Path
    source: str  # "user" | "project"
    disable_model_invocation: bool = False
    license: Optional[str] = None
    compatibility: Optional[str] = None
    allowed_tools: Optional[str] = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class LoadSkillsResult:
    """Result of loading skills from configured directories."""

    skills: list[Skill]
    diagnostics: list["SkillDiagnostic"]


@dataclass
class SkillDiagnostic:
    """A diagnostic message (warning or error) about a skill."""

    type: str  # "warning" | "error"
    message: str
    path: str


def _normalize_nfkc(text: str) -> str:
    """Normalize text using NFKC form (for Unicode consistency)."""
    import unicodedata

    return unicodedata.normalize("NFKC", text.strip())


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from SKILL.md content.

    Args:
        content: Raw content of SKILL.md file

    Returns:
        Tuple of (metadata dict, markdown body)

    Raises:
        ValueError: If frontmatter is missing or invalid
    """
    if not content.startswith("---"):
        raise ValueError("SKILL.md must start with YAML frontmatter (---)")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md frontmatter not properly closed with ---")

    frontmatter_str = parts[1]
    body = parts[2].strip()

    # Parse YAML using PyYAML
    try:
        metadata = yaml.safe_load(frontmatter_str)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {e}")

    if metadata is None:
        metadata = {}
    elif not isinstance(metadata, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")

    # Convert all keys to strings for consistency
    metadata = {str(k): v for k, v in metadata.items()}

    return metadata, body


def find_skill_md(skill_dir: Path) -> Optional[Path]:
    """Find the SKILL.md file in a skill directory.

    Prefers SKILL.md (uppercase) but accepts skill.md (lowercase).

    Args:
        skill_dir: Path to the skill directory

    Returns:
        Path to the SKILL.md file, or None if not found
    """
    for name in ("SKILL.md", "skill.md"):
        path = skill_dir / name
        if path.exists():
            return path
    return None


def validate_name(name: str, skill_dir: Optional[Path] = None) -> list[str]:
    """Validate skill name format and directory match.

    Args:
        name: The skill name to validate
        skill_dir: Optional path to skill directory (for name-directory match check)

    Returns:
        List of validation error messages. Empty list means valid.
    """
    errors = []

    if not name or not isinstance(name, str) or not name.strip():
        errors.append("Field 'name' must be a non-empty string")
        return errors

    name = _normalize_nfkc(name)

    if len(name) > MAX_NAME_LENGTH:
        errors.append(
            f"Skill name '{name}' exceeds {MAX_NAME_LENGTH} character limit ({len(name)} chars)"
        )

    if name != name.lower():
        errors.append(f"Skill name '{name}' must be lowercase")

    if name.startswith("-") or name.endswith("-"):
        errors.append("Skill name cannot start or end with a hyphen")

    if "--" in name:
        errors.append("Skill name cannot contain consecutive hyphens")

    if not all(c.isalnum() or c == "-" for c in name):
        errors.append(
            f"Skill name '{name}' contains invalid characters. "
            "Only letters, digits, and hyphens are allowed."
        )

    if skill_dir:
        dir_name = _normalize_nfkc(skill_dir.name)
        if dir_name != name:
            errors.append(
                f"Directory name '{skill_dir.name}' must match skill name '{name}'"
            )

    return errors


def validate_description(description: str) -> list[str]:
    """Validate description format.

    Args:
        description: The description to validate

    Returns:
        List of validation error messages. Empty list means valid.
    """
    errors = []

    if not description or not isinstance(description, str) or not description.strip():
        errors.append("Field 'description' must be a non-empty string")
        return errors

    if len(description) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            f"Description exceeds {MAX_DESCRIPTION_LENGTH} character limit ({len(description)} chars)"
        )

    return errors


def validate_compatibility(compatibility: str) -> list[str]:
    """Validate compatibility format.

    Args:
        compatibility: The compatibility string to validate

    Returns:
        List of validation error messages. Empty list means valid.
    """
    errors = []

    if not isinstance(compatibility, str):
        errors.append("Field 'compatibility' must be a string")
        return errors

    if len(compatibility) > MAX_COMPATIBILITY_LENGTH:
        errors.append(
            f"Compatibility exceeds {MAX_COMPATIBILITY_LENGTH} character limit ({len(compatibility)} chars)"
        )

    return errors


def validate_metadata_fields(metadata: dict) -> list[str]:
    """Validate that only allowed fields are present.

    Args:
        metadata: The parsed frontmatter metadata

    Returns:
        List of validation error messages. Empty list means valid.
    """
    errors = []

    extra_fields = set(metadata.keys()) - ALLOWED_FIELDS
    if extra_fields:
        errors.append(
            f"Unexpected fields in frontmatter: {', '.join(sorted(extra_fields))}. "
            f"Only {sorted(ALLOWED_FIELDS)} are allowed."
        )

    return errors


def validate(skill_dir: Path) -> list[str]:
    """Validate a skill directory.

    Args:
        skill_dir: Path to the skill directory

    Returns:
        List of validation error messages. Empty list means valid.
    """
    skill_dir = Path(skill_dir)

    if not skill_dir.exists():
        return [f"Path does not exist: {skill_dir}"]

    if not skill_dir.is_dir():
        return [f"Not a directory: {skill_dir}"]

    skill_md = find_skill_md(skill_dir)
    if skill_md is None:
        return ["Missing required file: SKILL.md"]

    try:
        content = skill_md.read_text(encoding="utf-8")
        metadata, _ = parse_frontmatter(content)
    except ValueError as e:
        return [str(e)]

    errors = []
    errors.extend(validate_metadata_fields(metadata))

    if "name" not in metadata:
        errors.append("Missing required field in frontmatter: name")
    else:
        errors.extend(validate_name(metadata["name"], skill_dir))

    if "description" not in metadata:
        errors.append("Missing required field in frontmatter: description")
    else:
        errors.extend(validate_description(metadata["description"]))

    if "compatibility" in metadata and metadata["compatibility"]:
        errors.extend(validate_compatibility(metadata["compatibility"]))

    return errors


def read_skill(skill_dir: Path, source: str) -> tuple[Optional[Skill], list[SkillDiagnostic]]:
    """Read a skill from a directory.

    Args:
        skill_dir: Path to the skill directory
        source: Source identifier ("user" or "project")

    Returns:
        Tuple of (Skill or None, list of diagnostics)
    """
    diagnostics: list[SkillDiagnostic] = []
    skill_dir = Path(skill_dir)

    if not skill_dir.exists() or not skill_dir.is_dir():
        return None, [SkillDiagnostic("error", f"Directory not found: {skill_dir}", str(skill_dir))]

    skill_md = find_skill_md(skill_dir)
    if skill_md is None:
        return None, [SkillDiagnostic("error", "Missing SKILL.md", str(skill_dir))]

    try:
        content = skill_md.read_text(encoding="utf-8")
        metadata, _ = parse_frontmatter(content)
    except ValueError as e:
        return None, [SkillDiagnostic("error", f"Failed to parse frontmatter: {e}", str(skill_md))]

    # Validate and collect warnings (but still load the skill)
    name_errors = validate_name(metadata.get("name"), skill_dir)
    for err in name_errors:
        diagnostics.append(SkillDiagnostic("warning", err, str(skill_md)))

    desc_errors = validate_description(metadata.get("description"))
    for err in desc_errors:
        diagnostics.append(SkillDiagnostic("warning", err, str(skill_md)))

    # Check for required fields - if missing description, don't load
    if not metadata.get("description") or not metadata.get("description").strip():
        return None, [SkillDiagnostic("error", "Missing required field: description", str(skill_md))]

    if not metadata.get("name") or not metadata.get("name").strip():
        return None, [SkillDiagnostic("error", "Missing required field: name", str(skill_md))]

    # Handle metadata dict if present
    skill_metadata = {}
    if "metadata" in metadata and isinstance(metadata["metadata"], dict):
        skill_metadata = {str(k): str(v) for k, v in metadata["metadata"].items()}

    return Skill(
        name=metadata["name"].strip(),
        description=metadata["description"].strip(),
        file_path=skill_md,
        base_dir=skill_dir,
        source=source,
        disable_model_invocation=metadata.get("disable-model-invocation", False) is True,
        license=metadata.get("license"),
        compatibility=metadata.get("compatibility"),
        allowed_tools=metadata.get("allowed-tools"),
        metadata=skill_metadata,
    ), diagnostics


def load_skills_from_dir(
    skill_dir: Path,
    source: str,
    ignore_patterns: Optional[list[str]] = None,
) -> LoadSkillsResult:
    """Load skills from a directory.

    Discovery rules:
    - Direct .md files in the root
    - Recursive SKILL.md under subdirectories

    Args:
        skill_dir: Directory to scan for skills
        source: Source identifier ("user" | "project")
        ignore_patterns: Optional list of patterns to ignore

    Returns:
        LoadSkillsResult with skills and diagnostics
    """
    skills: list[Skill] = []
    diagnostics: list[SkillDiagnostic] = []
    seen_paths: set[Path] = set()

    if not skill_dir.exists():
        return LoadSkillsResult(skills=[], diagnostics=[])

    ignore_patterns = ignore_patterns or []

    # Walk the directory
    for root, dirs, files in os.walk(skill_dir, followlinks=True):
        root_path = Path(root)

        # Skip hidden directories and node_modules
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]

        # Check if we should skip this directory
        rel_path = root_path.relative_to(skill_dir)
        if any(part in ignore_patterns for part in rel_path.parts):
            continue

        # Check for SKILL.md in this directory
        skill_md = find_skill_md(root_path)
        if skill_md and skill_md not in seen_paths:
            skill, diags = read_skill(root_path, source)
            if skill:
                # Resolve symlinks to detect duplicates
                try:
                    real_path = skill_md.resolve()
                except OSError:
                    real_path = skill_md

                if real_path not in seen_paths:
                    skills.append(skill)
                    seen_paths.add(real_path)
            diagnostics.extend(diags)

        # Also check for direct .md files in root (non-recursive)
        if root_path == skill_dir:
            for f in files:
                if f.endswith(".md") and f.lower() != "skill.md":
                    md_path = root_path / f
                    skill_name = f[:-3]  # Remove .md extension
                    # Create a synthetic skill from a standalone .md file
                    # This is useful for single-file skills
                    try:
                        content = md_path.read_text(encoding="utf-8")
                        metadata, _ = parse_frontmatter(content)
                        if metadata.get("name") and metadata.get("description"):
                            skill = Skill(
                                name=metadata["name"].strip(),
                                description=metadata["description"].strip(),
                                file_path=md_path,
                                base_dir=skill_dir,
                                source=source,
                                disable_model_invocation=metadata.get("disable-model-invocation", False) is True,
                                license=metadata.get("license"),
                                compatibility=metadata.get("compatibility"),
                                allowed_tools=metadata.get("allowed-tools"),
                            )
                            real_path = md_path.resolve()
                            if real_path not in seen_paths:
                                skills.append(skill)
                                seen_paths.add(real_path)
                    except (ValueError, OSError):
                        pass  # Skip invalid files

    return LoadSkillsResult(skills=skills, diagnostics=diagnostics)


def get_default_skill_dirs() -> tuple[Path, Path]:
    """Get default skill directories.

    Returns:
        Tuple of (global_dir, project_dir)
    """
    # Global: ~/.zac/skills
    global_dir = Path(os.path.expanduser("~/.zac/skills"))

    # Project: .zac/skills in cwd
    project_dir = Path.cwd() / ".zac" / "skills"

    return global_dir, project_dir


def load_skills(
    global_dir: Optional[Path] = None,
    project_dir: Optional[Path] = None,
    cwd: Optional[Path] = None,
) -> LoadSkillsResult:
    """Load skills from all configured locations.

    Args:
        global_dir: Global skills directory (default: ~/.zac/skills)
        project_dir: Project skills directory (default: {cwd}/.zac/skills)
        cwd: Current working directory (default: Path.cwd())

    Returns:
        LoadSkillsResult with skills and diagnostics
    """
    if global_dir is None or project_dir is None:
        default_global, default_project = get_default_skill_dirs()
        global_dir = global_dir or default_global
        project_dir = project_dir or default_project

    cwd = cwd or Path.cwd()

    # Adjust project_dir to be relative to cwd
    if not project_dir.is_absolute():
        project_dir = cwd / project_dir

    all_skills: list[Skill] = []
    all_diagnostics: list[SkillDiagnostic] = []
    seen_names: dict[str, Path] = {}

    # Load from global directory first
    global_result = load_skills_from_dir(global_dir, "user")
    for skill in global_result.skills:
        if skill.name not in seen_names:
            all_skills.append(skill)
            seen_names[skill.name] = skill.file_path
        else:
            all_diagnostics.append(SkillDiagnostic(
                "warning",
                f"Skill '{skill.name}' from '{skill.file_path}' conflicts with existing",
                str(skill.file_path),
            ))
    all_diagnostics.extend(global_result.diagnostics)

    # Load from project directory (project overrides global with same name)
    project_result = load_skills_from_dir(project_dir, "project")
    for skill in project_result.skills:
        if skill.name not in seen_names:
            all_skills.append(skill)
            seen_names[skill.name] = skill.file_path
        else:
            # Project skill takes precedence - replace global
            existing_idx = next(i for i, s in enumerate(all_skills) if s.name == skill.name)
            all_skills[existing_idx] = skill
            all_diagnostics.append(SkillDiagnostic(
                "warning",
                f"Project skill '{skill.name}' overrides global skill",
                str(skill.file_path),
            ))
    all_diagnostics.extend(project_result.diagnostics)

    return LoadSkillsResult(skills=all_skills, diagnostics=all_diagnostics)


def format_skills_for_prompt(skills: list[Skill]) -> str:
    """Format skills for inclusion in a system prompt.

    Uses XML format per Agent Skills specification.

    Args:
        skills: List of skills to format

    Returns:
        XML string for system prompt, or empty string if no skills
    """
    # Filter out skills with disable_model_invocation=True
    visible_skills = [s for s in skills if not s.disable_model_invocation]

    if not visible_skills:
        return ""

    import html

    lines = [
        "\n\nThe following skills provide specialized instructions for specific tasks.",
        "Use the read tool to load a skill's file when the task matches its description.",
        "When a skill file references a relative path, resolve it against the skill directory.",
        "",
        "<available_skills>",
    ]

    for skill in visible_skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{html.escape(skill.name)}</name>")
        lines.append(f"    <description>{html.escape(skill.description)}</description>")
        lines.append(f"    <location>{html.escape(str(skill.file_path))}</location>")
        lines.append("  </skill>")

    lines.append("</available_skills>")

    return "\n".join(lines)
