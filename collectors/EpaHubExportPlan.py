"""
Plan Clip and Ship download files and interpret Hub export responses.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from collectors.PlannedFile import is_generated_sidecar
from utils.file_utils import sanitize_filename

_PENDING = frozenset(
    {"inprogress", "in progress", "creating", "processing", "pending", "stale"}
)
_DEFAULT_FORMATS = ("csv", "geojson", "shapefile", "kml", "excel", "geopackage", "filegdb")
_DOWNLOAD_ROOT = "https://edg-epa.hub.arcgis.com/api/download/v1/items"
_ITEM_DATA = "https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"
_SUFFIXES = {
    "csv": ".csv",
    "geojson": ".geojson",
    "excel": ".xlsx",
    "geopackage": ".gpkg",
    "sqlite": ".sqlite",
    "kml": ".kml",
    "featurecollection": ".json",
}
_ITEM_ID = re.compile(r"[0-9a-fA-F]{32}")
_LAYER_SUFFIX = re.compile(r"_[0-9]+$")


@dataclass(frozen=True)
class ReadyFile:
    """A generated export that can be saved."""

    file_url: str
    size_bytes: int | None
    error: str | None = None


def file_specs(feature: dict[str, Any], service: dict[str, Any]) -> list[tuple[str, str]]:
    """
    Return ``(filename, url)`` pairs for this item's data files.

    Args:
        feature: Hub search feature.
        service: Parsed FeatureServer JSON, or an empty object.

    Returns:
        Download filename and URL pairs.
    """
    definition = _service_definition_spec(feature)
    if definition is not None:
        return [definition]
    item_id = download_item_id(feature)
    if not item_id or not service:
        return []
    specs: list[tuple[str, str]] = []
    for layer_id, layer_name in _layers(service):
        for fmt in _formats(service):
            name = sanitize_filename(f"{layer_name}_{fmt}{_suffix(fmt)}")
            url = f"{_DOWNLOAD_ROOT}/{item_id}/{fmt}?layers={layer_id}&redirect=false"
            specs.append((name, url))
    return specs


def download_item_id(feature: dict[str, Any]) -> str:
    """
    Return the ArcGIS item id accepted by the Hub download API.

    Hub search features append ``_0`` (the layer) to the item id. The download
    API rejects that suffix.

    Args:
        feature: Hub search feature.

    Returns:
        Item id without a layer suffix.
    """
    properties = feature.get("properties")
    props = properties if isinstance(properties, dict) else {}
    raw = str(feature.get("id") or "").strip()
    for candidate in (str(props.get("id") or "").strip(), raw):
        normalized = _LAYER_SUFFIX.sub("", candidate)
        if _ITEM_ID.fullmatch(normalized):
            return normalized.lower()
    return _LAYER_SUFFIX.sub("", raw) or raw


def ready_from_response(response: Any) -> ReadyFile | None:
    """
    Interpret one download response.

    Args:
        response: HTTP response from the export endpoint.

    Returns:
        A ready file, an error result, or None when the caller should poll again.
    """
    status_code = int(getattr(response, "status_code", 500))
    if status_code in {301, 302, 303, 307, 308}:
        return _ready_redirect(response)
    if status_code >= 400:
        detail = _export_error(response, status_code)
        close_response(response)
        return ReadyFile("", None, detail)
    content_type = str(response.headers.get("Content-Type") or "")
    if status_code == 202 or "json" in content_type.lower():
        return _ready_from_json(response)
    file_url = str(getattr(response, "url", "") or "")
    size = content_length(response)
    close_response(response)
    return ReadyFile(file_url, size, None)


def content_length(response: Any) -> int | None:
    """
    Return Content-Length when it is a positive integer.

    Args:
        response: HTTP response.

    Returns:
        Byte length, or None.
    """
    return _int_or_none(response.headers.get("Content-Length"))


def _export_error(response: Any, status_code: int) -> str:
    """Return an unsupported-format label, or the HTTP status."""
    message = ""
    try:
        payload = response.json()
    except (TypeError, ValueError, AttributeError):
        payload = None
    if isinstance(payload, dict):
        message = str(payload.get("message") or "")
    if "unsupported file format" in message.casefold():
        return "unsupported file format"
    return f"export HTTP {status_code}"


def close_response(response: Any) -> None:
    """
    Close a streamed response when it has a close method.

    Args:
        response: HTTP response.
    """
    closer = getattr(response, "close", None)
    if callable(closer):
        closer()


def bytes_on_disk(folder: Path) -> int:
    """
    Return bytes already stored in ``folder``, ignoring generated PDFs.

    Args:
        folder: Project output folder.

    Returns:
        Byte total of data files.
    """
    if not folder.is_dir():
        return 0
    return sum(
        path.stat().st_size
        for path in folder.rglob("*")
        if path.is_file() and not is_generated_sidecar(path)
    )


def _service_definition_spec(feature: dict[str, Any]) -> tuple[str, str] | None:
    """Return the item-data download for a Service Definition, if this is one."""
    properties = feature.get("properties")
    props = properties if isinstance(properties, dict) else {}
    if str(props.get("type") or "").strip().casefold() != "service definition":
        return None
    item_id = download_item_id(feature)
    name = sanitize_filename(str(props.get("name") or f"{item_id}.sd"))
    return name, _ITEM_DATA.format(item_id=item_id)


def _formats(service: dict[str, Any]) -> list[str]:
    """Return export formats advertised by the service, or the default list.

    SQLite geodatabases are omitted. They repeat the CSV and file geodatabase,
    and DataLumos rejects the file.
    """
    raw = str(service.get("supportedExportFormats") or "")
    found = [part.strip() for part in raw.split(",") if part.strip()]
    formats = found or list(_DEFAULT_FORMATS)
    return [fmt for fmt in formats if fmt.casefold() != "sqlite"]


def _layers(service: dict[str, Any]) -> list[tuple[int, str]]:
    """Return ``(layer id, layer name)`` pairs, defaulting to layer 0."""
    layers = service.get("layers")
    parsed: list[tuple[int, str]] = []
    if isinstance(layers, list):
        for layer in layers:
            if not isinstance(layer, dict) or layer.get("id") is None:
                continue
            name = str(layer.get("name") or f"layer_{layer['id']}").strip()
            parsed.append((int(layer["id"]), name or f"layer_{layer['id']}"))
    return parsed or [(0, "layer")]


def _suffix(fmt: str) -> str:
    """Return a filename suffix for a Hub export format."""
    return _SUFFIXES.get(fmt.strip().casefold(), ".zip")


def name_with_export_extension(name: str, file_url: str) -> str:
    """Use the generated file's extension when the result URL has one.

    Args:
        name: Planned download name.
        file_url: URL of the file Hub generated.

    Returns:
        ``name`` with the result URL's extension, or ``name`` unchanged.
    """
    suffix = _extension_from_url(file_url)
    planned = PurePosixPath(name)
    if not suffix or planned.suffix.lower() != ".zip" or suffix == ".zip":
        return name
    return str(planned.with_suffix(suffix))


def corrected_zip_export(path: Path) -> Path:
    """Rename an export whose extension does not match its bytes.

    A ``.zip`` that is KML or JSON takes that extension. A ``.kml`` that is a
    zipped KMZ becomes ``.kmz``.

    Args:
        path: File already saved by an earlier collect.

    Returns:
        The file to keep. A mismatched name is renamed in place.
    """
    if not path.is_file():
        return path
    suffix = _extension_for_content(path)
    current = path.suffix.lower()
    if not suffix or suffix == current:
        return path
    if current != ".zip" and not (current == ".kml" and suffix == ".kmz"):
        return path
    dest = path.with_suffix(suffix)
    if dest == path:
        return path
    if dest.is_file() and dest.stat().st_size > 0:
        path.unlink()
        return dest
    if dest.exists():
        dest.unlink()
    path.rename(dest)
    return dest


def _extension_from_url(url: str) -> str:
    """Return the lowercase extension on a result URL, including the dot."""
    suffix = PurePosixPath(unquote(urlparse(url).path)).suffix.lower()
    if suffix and suffix[1:].isalnum():
        return suffix
    return ""


def _extension_for_content(path: Path) -> str | None:
    """Return the extension the saved bytes actually are."""
    try:
        head = path.read_bytes()[:1024]
    except OSError:
        return None
    stripped = head.lstrip()
    lowered = stripped.lower()
    if b"<kml" in lowered:
        return ".kml"
    if stripped.startswith((b"{", b"[")):
        return ".json"
    if head.startswith(b"PK") and _zip_has_kml(path):
        return ".kmz"
    return None


def _zip_has_kml(path: Path) -> bool:
    """Return True when a zip archive contains a KML member."""
    try:
        with zipfile.ZipFile(path) as archive:
            return any(name.lower().endswith(".kml") for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def _ready_redirect(response: Any) -> ReadyFile:
    """Return the redirect target as the file URL."""
    location = str(response.headers.get("Location") or "")
    close_response(response)
    if not location:
        return ReadyFile("", None, "export redirect was missing")
    return ReadyFile(location, None, None)


def _ready_from_json(response: Any) -> ReadyFile | None:
    """Return a ready file from a JSON status body, or None to keep polling."""
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    request_url = str(getattr(response, "url", "") or "")
    close_response(response)
    if not isinstance(payload, dict):
        return ReadyFile(request_url, None, "export response was not JSON")
    status = str(payload.get("status") or "").strip().casefold()
    if status in _PENDING:
        return None
    file_url = _export_file_url(payload)
    size = _int_or_none(payload.get("contentLength"))
    if size is None:
        size = _int_or_none(payload.get("size"))
    if file_url:
        return ReadyFile(file_url, size, None)
    if status in {"error", "failed"}:
        return ReadyFile(request_url, None, f"export {status}")
    if status in {"completed", "complete", "ready", "success", "succeeded"}:
        return ReadyFile(request_url, None, "export finished without a file url")
    return None


def _export_file_url(payload: dict[str, Any]) -> str:
    """Return the file URL from a Hub export status body."""
    lowered = {str(key).casefold(): value for key, value in payload.items()}
    for key in ("downloadurl", "resulturl", "url"):
        text = str(lowered.get(key) or "").strip()
        if text:
            return text
    return ""


def _int_or_none(value: Any) -> int | None:
    """Return a positive int, or None."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number
