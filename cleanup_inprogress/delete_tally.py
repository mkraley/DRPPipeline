"""Success and failure counts for a DataLumos delete run."""

from dataclasses import dataclass, field


@dataclass
class DeleteTally:
    """Running count of project deletes that succeeded or failed."""

    successes: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)

    def record_success(self, workspace_id: str) -> None:
        """
        Record one deleted project.

        Args:
            workspace_id: Numeric DataLumos project id.
        """
        self.successes.append(workspace_id)

    def record_failure(self, workspace_id: str, detail: str) -> None:
        """
        Record one project that could not be deleted.

        Args:
            workspace_id: Numeric DataLumos project id.
            detail: Why the delete failed.
        """
        self.failures.append((workspace_id, detail))

    @property
    def success_count(self) -> int:
        """Return how many deletes succeeded."""
        return len(self.successes)

    @property
    def failure_count(self) -> int:
        """Return how many deletes failed."""
        return len(self.failures)

    def summary(self) -> str:
        """Return a one-line success and failure tally."""
        return f"successes={self.success_count} failures={self.failure_count}"
