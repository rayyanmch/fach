"""ILIAS-Anbindung. Nach außen nur: Backend-Schnittstelle, Modelle, Fehler (siehe models.py)."""

from .models import AuthFailed, CourseResult, FoundCourse, IliasBackend, IliasError, Unreachable

__all__ = ["AuthFailed", "CourseResult", "FoundCourse", "IliasBackend", "IliasError", "Unreachable"]
