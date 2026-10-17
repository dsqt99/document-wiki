"""Permission catalogue, the four global roles and the role -> permission matrix.

Permissions are strings of the form ``resource:action[:scope]`` where scope is
``own_dept`` or ``all``. The default matrix can be overridden per role (except
``admin``) through the ``role_permissions_custom`` config key; the override is
held in process memory and reloaded on startup and after each matrix save.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = ("own_dept", "all")


def _scoped(resource: str, actions: tuple[str, ...]) -> list[str]:
    return [f"{resource}:{action}:{scope}" for action in actions for scope in SCOPES]


_DOC_ACTIONS = ("read", "create", "edit", "delete")
_WIKI_ACTIONS = ("read", "write", "delete")
_SKILL_ACTIONS = ("read", "create", "edit", "delete")

PERMISSION_GROUPS: dict[str, list[str]] = {
    "Documents": _scoped("doc", _DOC_ACTIONS),
    "Wiki": _scoped("wiki", _WIKI_ACTIONS),
    "AI Skills": _scoped("skill", _SKILL_ACTIONS) + ["skill:contribution:review"],
    "Organization": [
        "org:departments:read",
        "org:departments:manage",
        "org:employees:read",
        "org:employees:manage",
        "org:roles:read",
        "org:roles:manage",
        "org:settings:read",
        "org:settings:manage",
        "org:audit:read",
    ],
    "Workspaces": ["workspace:view:all"],
}

ALL_PERMISSIONS: list[str] = [p for perms in PERMISSION_GROUPS.values() for p in perms]
_ALL_SET = frozenset(ALL_PERMISSIONS)

_RESOURCE_NAMES = {"doc": "documents", "wiki": "wiki pages", "skill": "AI skills"}
_ACTION_VERBS = {
    "read": "Read",
    "create": "Create",
    "edit": "Edit",
    "write": "Write",
    "delete": "Delete",
}
_SCOPE_TEXT = {
    "own_dept": ("(own units)", "in the units the user belongs to, plus global ones"),
    "all": ("(all units)", "across every unit"),
}

PERMISSION_LABELS: dict[str, str] = {}
PERMISSION_DESCRIPTIONS: dict[str, str] = {}

for _resource, _actions in (("doc", _DOC_ACTIONS), ("wiki", _WIKI_ACTIONS), ("skill", _SKILL_ACTIONS)):
    for _action in _actions:
        for _scope in SCOPES:
            _key = f"{_resource}:{_action}:{_scope}"
            _short, _long = _SCOPE_TEXT[_scope]
            PERMISSION_LABELS[_key] = f"{_ACTION_VERBS[_action]} {_RESOURCE_NAMES[_resource]} {_short}"
            PERMISSION_DESCRIPTIONS[_key] = (
                f"{_ACTION_VERBS[_action]} {_RESOURCE_NAMES[_resource]} {_long}."
            )

PERMISSION_LABELS.update(
    {
        "skill:contribution:review": "Review skill contributions",
        "org:departments:read": "View departments",
        "org:departments:manage": "Manage departments",
        "org:employees:read": "View employees",
        "org:employees:manage": "Manage employees",
        "org:roles:read": "View role matrix",
        "org:roles:manage": "Edit role matrix",
        "org:settings:read": "View system settings",
        "org:settings:manage": "Change system settings",
        "org:audit:read": "View audit log",
        "workspace:view:all": "See every workspace",
    }
)
PERMISSION_DESCRIPTIONS.update(
    {
        "skill:contribution:review": "Approve or reject skills submitted by contributors.",
        "org:departments:read": "List departments and their members.",
        "org:departments:manage": "Create, rename and remove local departments.",
        "org:employees:read": "List employee accounts.",
        "org:employees:manage": "Create, edit, deactivate employees and issue MCP tokens.",
        "org:roles:read": "See which permissions each role holds.",
        "org:roles:manage": "Change the permissions granted to each role.",
        "org:settings:read": "Read the AI, OCR and processing configuration.",
        "org:settings:manage": "Change the AI, OCR and processing configuration.",
        "org:audit:read": "Read and verify the audit trail.",
        "workspace:view:all": "Legacy: view all workspaces.",
    }
)

SYSTEM_ROLES: list[dict[str, str]] = [
    {
        "id": "viewer",
        "name": "Viewer (Người xem)",
        "description": "Reads documents, wiki pages and skills of their own units and global ones.",
    },
    {
        "id": "contributor",
        "name": "Contributor (Người đóng góp)",
        "description": "Viewer rights plus uploading documents, writing wiki pages and proposing skills in their units.",
    },
    {
        "id": "knowledge_manager",
        "name": "Knowledge Manager (Quản trị tri thức)",
        "description": "Manages all knowledge across units, reviews contributions and the organisation tree.",
    },
    {
        "id": "admin",
        "name": "System Admin (Quản trị viên)",
        "description": "Full control of the system. Always holds every permission.",
    },
]
SYSTEM_ROLE_IDS = [r["id"] for r in SYSTEM_ROLES]

_ORG_READ = ["org:departments:read", "org:employees:read"]

_VIEWER = ["doc:read:own_dept", "wiki:read:own_dept", "skill:read:own_dept"] + _ORG_READ

_CONTRIBUTOR = [
    "doc:read:own_dept",
    "doc:create:own_dept",
    "wiki:read:own_dept",
    "wiki:write:own_dept",
    "skill:read:own_dept",
    "skill:create:own_dept",
] + _ORG_READ

_KNOWLEDGE_MANAGER = (
    [f"doc:{a}:all" for a in _DOC_ACTIONS]
    + [f"wiki:{a}:all" for a in _WIKI_ACTIONS]
    + [f"skill:{a}:all" for a in _SKILL_ACTIONS]
    + [
        "skill:contribution:review",
        "org:departments:read",
        "org:departments:manage",
        "org:employees:read",
        "org:employees:manage",
        "org:audit:read",
    ]
)

ROLE_PERMISSIONS_MAP: dict[str, list[str]] = {
    "viewer": _VIEWER,
    "contributor": _CONTRIBUTOR,
    "knowledge_manager": _KNOWLEDGE_MANAGER,
    "admin": list(ALL_PERMISSIONS),
}

ROLE_PRESETS: dict[str, list[str]] = {role: list(perms) for role, perms in ROLE_PERMISSIONS_MAP.items()}

EMPLOYEE_DEFAULT_PERMISSIONS: list[str] = [
    "doc:read:own_dept",
    "doc:create:own_dept",
    "wiki:read:own_dept",
    "wiki:write:own_dept",
    "skill:read:own_dept",
    "org:departments:read",
]

LEGACY_PERMISSION_MAP: dict[str, list[str]] = {
    f"{resource}:{action}": [f"{resource}:{action}:{scope}" for scope in SCOPES]
    for resource, actions in (("doc", _DOC_ACTIONS), ("wiki", _WIKI_ACTIONS), ("skill", _SKILL_ACTIONS))
    for action in actions
}

_overrides: dict[str, list[str]] = {}


def _clean(perms) -> list[str]:
    if not isinstance(perms, (list, tuple, set)):
        return []
    seen: list[str] = []
    for p in perms:
        if isinstance(p, str) and p in _ALL_SET and p not in seen:
            seen.append(p)
    return seen


def sanitize_role_permissions(raw) -> dict[str, list[str]]:
    """Drop the admin role and any unknown permission from a role -> permissions mapping."""
    if not isinstance(raw, dict):
        return {}
    return {
        str(role): _clean(perms)
        for role, perms in raw.items()
        if str(role) != "admin"
    }


def load_role_permissions_override(json_str: Optional[str]) -> None:
    """Replace the in-memory override from a JSON object string. Invalid JSON is ignored."""
    global _overrides
    if not json_str:
        return
    try:
        data = json.loads(json_str)
    except (TypeError, ValueError):
        logger.warning("Ignoring invalid role_permissions_custom value")
        return
    if not isinstance(data, dict):
        logger.warning("Ignoring role_permissions_custom: not a JSON object")
        return
    _overrides = sanitize_role_permissions(data)


def get_effective_role_permissions() -> dict[str, list[str]]:
    result = {role: list(perms) for role, perms in ROLE_PERMISSIONS_MAP.items()}
    for role, perms in _overrides.items():
        if role != "admin":
            result[role] = list(perms)
    result["admin"] = list(ALL_PERMISSIONS)
    return result
