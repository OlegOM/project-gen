from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class PlanFile:
    """Represents a single file to be generated."""

    path: str
    role: str
    depends_on: List[str]
    contracts: List[str]


def _validate_spec(spec: Dict[str, Any]) -> None:
    """Ensure required sections exist in the specification."""

    stacks = spec.get("stacks") or {}
    if "backend" not in stacks or "frontend" not in stacks:
        raise ValueError("spec must contain 'stacks.backend' and 'stacks.frontend'")


def _backend_files(spec: Dict[str, Any]) -> List[PlanFile]:
    be = spec["stacks"]["backend"]
    be_fw = (be.get("framework") or "").lower()
    be_lang = (be.get("lang") or "").lower()
    files: List[PlanFile] = []

    if be_fw in {"fastapi", "django"} or be_lang == "python":
        files.extend(
            [
                PlanFile(
                    "backend/app/main.py",
                    "entrypoint",
                    [],
                    ["GET /health returns 200 {status:'ok'}"],
                ),
                PlanFile("backend/app/models/__init__.py", "pkg", [], []),
                PlanFile("backend/app/routes/__init__.py", "pkg", [], []),
                PlanFile("backend/app/workflows/__init__.py", "pkg", [], []),
                PlanFile(
                    "tests/test_health.py",
                    "test",
                    ["backend/app/main.py"],
                    ["GET /health == 200"],
                ),
                PlanFile("backend/requirements.txt", "deps", [], []),
                PlanFile("pytest.ini", "test_config", [], []),
            ]
        )
        for ent in spec.get("entities") or []:
            ename = ent["name"].lower()
            files.append(
                PlanFile(
                    f"backend/app/models/{ename}.py",
                    "model",
                    [],
                    [f"Model for {ent['name']}",],
                )
            )
            files.append(
                PlanFile(
                    f"backend/app/routes/{ename}s.py",
                    "api",
                    [f"backend/app/models/{ename}.py"],
                    [f"CRUD for {ent['name']}",],
                )
            )

        for wf in spec.get("workflows") or []:
            wname = wf.get("name", "").replace(" ", "_").lower()
            files.append(
                PlanFile(
                    f"backend/app/workflows/{wname}.py",
                    "workflow",
                    [],
                    [f"Workflow for {wf.get('name','')}"],
                )
            )

    return files


def _frontend_files(spec: Dict[str, Any]) -> List[PlanFile]:
    fe = spec["stacks"]["frontend"]
    fe_fw = (fe.get("framework") or "").lower()
    fe_lang = (fe.get("lang") or "").lower()

    if fe_fw == "react" and fe_lang == "ts":
        return [
            PlanFile("frontend/index.html", "page", [], ["Mounts #root"]),
            PlanFile("frontend/src/main.tsx", "entry", [], ["Renders app title"]),
            PlanFile("frontend/tsconfig.json", "tsconfig", [], []),
            PlanFile("frontend/package.json", "deps", [], []),
            PlanFile("frontend/vite.config.ts", "vite", [], []),
        ]

    return [
        PlanFile("frontend/index.html", "page", [], ["Shows app title"]),
    ]


def _infra_files() -> List[PlanFile]:
    return [
        PlanFile(
            "infra/docker-compose.yml",
            "compose",
            [],
            ["api, frontend, db services"],
        )
    ]


def spec_to_fileplan(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a file plan from a project specification."""

    _validate_spec(spec)
    libs = spec.get("constraints", {}).get("allowed_libs", {})

    files: List[PlanFile] = []
    files.extend(_backend_files(spec))
    files.extend(_frontend_files(spec))
    files.extend(_infra_files())

    logger.debug("Generated %d file entries", len(files))
    return {"files": [asdict(f) for f in files], "libraries": libs}

