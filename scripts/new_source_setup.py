"""Plan a new pipeline source: config section, paths, and sheet tab name."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from utils.source_sheet_defaults import new_source_sheet_defaults

_SOURCE_CODE = re.compile(r"[a-z]{2,10}")


def normalize_source_code(raw: str) -> str:
    """
    Return a lowercase source code.

    Args:
        raw: Initials typed on the command line.

    Returns:
        Lowercase letters, 2–10 characters.

    Raises:
        ValueError: If ``raw`` is not a short alphabetic code.
    """
    code = raw.strip().lower()
    if _SOURCE_CODE.fullmatch(code) is None:
        raise ValueError("Source initials must be 2–10 letters, for example nrc.")
    return code


def tab_name_for(code: str) -> str:
    """
    Return the inventory worksheet title for a source code.

    Args:
        code: Lowercase source code.

    Returns:
        Uppercase tab name, such as ``NRC``.
    """
    return code.upper()


def choose_template_source(
    config: dict[str, Any],
    requested: str | None,
) -> tuple[str, dict[str, Any]]:
    """
    Select the existing source whose spreadsheet will be copied.

    Args:
        config: Parsed config.json object.
        requested: ``--template`` value, or None to use the active source.

    Returns:
        Source key and its config section.

    Raises:
        ValueError: If the template is missing or has no spreadsheet id.
    """
    sources = config.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("config.json has no sources object.")
    name = (requested or str(config.get("source") or "")).strip().lower()
    if not name:
        raise ValueError("Pass --template; config.json has no active source.")
    section = sources.get(name)
    if not isinstance(section, dict):
        known = ", ".join(sorted(str(key) for key in sources))
        raise ValueError(f"Template source '{name}' was not found. Sources: {known}")
    if not str(section.get("google_sheet_id") or "").strip():
        raise ValueError(f"Template source '{name}' has no google_sheet_id.")
    if not str(section.get("google_sheet_name") or "").strip():
        raise ValueError(f"Template source '{name}' has no google_sheet_name.")
    return name, section


def output_directory(template_output: str, tab_name: str) -> str:
    """
    Return the download folder for a new source.

    Args:
        template_output: ``base_output_dir`` of the template source.
        tab_name: Uppercase source tab name.

    Returns:
        A sibling directory named ``{tab_name}Data``.
    """
    parent = Path(template_output).parent if template_output.strip() else Path(r"C:\DataRescue")
    return str(parent / f"{tab_name}Data")


def datalumos_username_for(template_username: str, code: str) -> str:
    """
    Suggest a plus-addressed DataLumos login from the template account.

    Args:
        template_username: Template source's ``datalumos_username``.
        code: New lowercase source code.

    Returns:
        ``prefix+code@domain`` when the template uses a plus address, else ``""``.
    """
    username = template_username.strip()
    if "@" not in username:
        return ""
    local, domain = username.split("@", 1)
    if "+" not in local:
        return ""
    prefix = local.split("+", 1)[0]
    return f"{prefix}+{code}@{domain}"


def build_source_config(
    code: str,
    template: dict[str, Any],
    sheet_id: str,
    contact: str | None,
) -> dict[str, Any]:
    """
    Build the ``sources.<code>`` object for a new source.

    DataLumos password is left empty. Source-specific template keys (catalog
    URLs, API tokens, Globus credentials) are not copied.

    Args:
        code: Lowercase source code.
        template: Template source section.
        sheet_id: New spreadsheet id.
        contact: Baserow contact email when the template has none.

    Returns:
        Config section for the new source.
    """
    tab_name = tab_name_for(code)
    template_contact = str(template.get("baserow_contact") or contact or "")
    section: dict[str, Any] = {
        "base_output_dir": output_directory(str(template.get("base_output_dir") or ""), tab_name),
        "google_sheet_name": tab_name,
        "db_path": f"{code}.db",
        "sourcing_url_prefix": "",
        "datalumos_username": datalumos_username_for(
            str(template.get("datalumos_username") or ""),
            code,
        ),
        "datalumos_password": "",
        "google_sheet_id": sheet_id,
    }
    section.update(new_source_sheet_defaults(template_contact))
    return section


def assert_source_available(config: dict[str, Any], code: str, config_dir: Path) -> None:
    """
    Reject a source code that already has a config section or database.

    Args:
        config: Parsed config.json object.
        code: Proposed source code.
        config_dir: Directory that holds ``config.json`` and ``*.db`` files.

    Raises:
        ValueError: If the source or its database already exists.
    """
    sources = config.get("sources")
    if isinstance(sources, dict) and code in sources:
        raise ValueError(f"Source '{code}' already exists in config.")
    database = config_dir / f"{code}.db"
    if database.exists():
        raise ValueError(f"Database already exists: {database}")


def assert_output_dir_available(path: Path) -> None:
    """
    Reject an output directory that already contains files.

    Args:
        path: Proposed ``base_output_dir``.

    Raises:
        ValueError: If ``path`` exists and is not empty.
    """
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"Output directory is not empty: {path}")


def apply_new_source(config: dict[str, Any], code: str, section: dict[str, Any]) -> None:
    """
    Insert a source section and make it the active source.

    Args:
        config: Parsed config object, updated in place.
        code: New source code.
        section: ``sources.<code>`` object.

    Raises:
        ValueError: If ``sources`` is not an object.
    """
    sources = config.setdefault("sources", {})
    if not isinstance(sources, dict):
        raise ValueError("config sources must be an object.")
    sources[code] = section
    config["source"] = code
