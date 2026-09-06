"""JSON artifact builder for mathematical AI feed."""

from dataclasses import asdict
import json
import logging
import os
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


def _json_serializer(obj: Any) -> Any:
    """Helper to serialize dataclass or objects with to_dict method."""
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def build_json(aggregated_data: dict[str, Any], output_path: str = "public/latest.json") -> None:
    """Serialize aggregated data to formatted JSON and write atomically.

    Args:
        aggregated_data: Dictionary containing 'updated_at' and 'pillars' keys.
        output_path: File system path where JSON will be written.

    Raises:
        ValueError: If required root keys are missing.
    """
    if not isinstance(aggregated_data, dict):
        raise ValueError("aggregated_data must be a dictionary")

    if "updated_at" not in aggregated_data or "pillars" not in aggregated_data:
        raise ValueError(
            "Invalid aggregated_data: missing required root keys ('updated_at', 'pillars')"
        )

    if not isinstance(aggregated_data["pillars"], dict):
        raise ValueError("Invalid aggregated_data: 'pillars' must be a dictionary")

    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)

    tmp_file = tempfile.NamedTemporaryFile(
        "w", dir=output_dir, delete=False, suffix=".tmp", encoding="utf-8"
    )
    tmp_path = tmp_file.name

    try:
        with tmp_file as f:
            json.dump(
                aggregated_data,
                f,
                indent=2,
                default=_json_serializer,
                ensure_ascii=False,
            )
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, output_path)
        logger.info("Successfully wrote JSON artifact to %s", output_path)
    except Exception as exc:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        logger.error("Failed to write JSON artifact to %s: %s", output_path, exc)
        raise
