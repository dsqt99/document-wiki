"""Bounded passive resources accompanying a skill version in internal synchronization."""

import logging
from pathlib import PurePosixPath

log = logging.getLogger(__name__)


async def collect_skill_resources(skill_md_path, files, download):
    resources = {}
    total_bytes = 0
    root = PurePosixPath(skill_md_path).parent if skill_md_path else PurePosixPath(".")
    for path, obj in files:
        try:
            relative = PurePosixPath(path).relative_to(root)
        except ValueError:
            continue
        if (
            not relative.parts
            or relative.parts[0] not in {"references", "templates"}
            or ".." in relative.parts
            or "\\" in str(relative)
            or relative.suffix not in {".json", ".md", ".txt", ".yaml", ".yml"}
            or (getattr(obj, "size", 0) or 0) > 65536
            or len(resources) >= 24
        ):
            continue
        try:
            data = await download(obj.object_name)
            if data is None or len(data) > 65536 or total_bytes + len(data) > 262144:
                continue
            resources[relative.as_posix()] = data.decode("utf-8")
            total_bytes += len(data)
        except (OSError, UnicodeDecodeError):
            log.warning("Skill reference unavailable: %s", relative)
        except Exception as exc:
            # An unavailable optional object must not disable the entire skill catalogue.
            log.warning("Skill reference unavailable: %s (%s)", relative, type(exc).__name__)
    return resources
