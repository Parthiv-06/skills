"""Small string helpers for building URL- and file-safe identifiers.
slugify keeps ASCII letters and digits only; accents are dropped, not transliterated."""
import re


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
