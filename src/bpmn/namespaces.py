"""Namespace and XML helper utilities for BPMN documents."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


BPMN_MODEL_URI = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMN_DI_URI = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_URI = "http://www.omg.org/spec/DD/20100524/DC"
DI_URI = "http://www.omg.org/spec/DD/20100524/DI"


def local_name(value: str) -> str:
    """Return the local part of an XML QName."""

    if value.startswith("{"):
        return value.rsplit("}", 1)[1]

    if ":" in value:
        return value.rsplit(":", 1)[1]

    return value


def normalize_text(value: str | None) -> str | None:
    """Trim and normalize whitespace in XML text."""

    if value is None:
        return None

    normalized = " ".join(value.split())
    return normalized or None


def collect_namespaces(path: Path) -> dict[str, str]:
    """Collect namespaces declared in an XML document."""

    namespaces: dict[str, str] = {}

    for _, item in ET.iterparse(path, events=("start-ns",)):
        prefix, uri = item
        namespaces[prefix or "default"] = uri

    return namespaces


@dataclass(frozen=True)
class NamespaceContext:
    """Namespace information and helper methods for BPMN parsing."""

    prefix_to_uri: dict[str, str]

    @property
    def uri_to_prefix(self) -> dict[str, str]:
        return {
            uri: prefix
            for prefix, uri in self.prefix_to_uri.items()
        }

    def qname(self, local: str, uri: str = BPMN_MODEL_URI) -> str:
        """Return an ElementTree-compatible expanded QName."""

        return f"{{{uri}}}{local}"

    def readable_name(self, value: str) -> str:
        """Convert an expanded QName into a readable prefixed name."""

        if not value.startswith("{"):
            return value

        uri, local = value[1:].split("}", 1)
        prefix = self.uri_to_prefix.get(uri)

        if prefix and prefix != "default":
            return f"{prefix}:{local}"

        return local

    def attributes(self, element: ET.Element) -> dict[str, str]:
        """Return readable element attributes."""

        return {
            self.readable_name(key): value
            for key, value in sorted(
                element.attrib.items(),
                key=lambda item: self.readable_name(item[0]),
            )
        }


def first_child_text(
    element: ET.Element,
    child_local_name: str,
) -> str | None:
    """Return normalized text from the first matching child."""

    for child in list(element):
        if local_name(child.tag) == child_local_name:
            return normalize_text(child.text)

    return None


def child_texts(
    element: ET.Element,
    child_local_name: str,
) -> list[str]:
    """Return normalized text values from matching children."""

    values: list[str] = []

    for child in list(element):
        if local_name(child.tag) != child_local_name:
            continue

        text = normalize_text(child.text)

        if text is not None:
            values.append(text)

    return values