"""规则包加载与 status 门控（迁自来源 ``rules.loader`` / ``rules.gate``）。

规则包按「依据文件 × 版本」组织；金额用 ``parse_float=Decimal``。
门控按作用域（calc / late / reduction / check）：只校验本次计算引用的条目。
"""

import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from . import registry
from .errors import RulesetError

MANIFEST_NAME = "rules-manifest.json"
SCHEMA_MANIFEST = "patfee.rules.manifest/v1"
SCHEMA_RULESET = "patfee.ruleset/v1"

STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"
STATUS_INPUT_REQUIRED = "input_required"
VALID_STATUS = (STATUS_VERIFIED, STATUS_PENDING, STATUS_INPUT_REQUIRED)

SCOPE_CALC = "calc"
SCOPE_LATE = "late"
SCOPE_REDUCTION = "reduction"
SCOPE_CHECK = "check"
ALL_SCOPES = (SCOPE_CALC, SCOPE_LATE, SCOPE_REDUCTION, SCOPE_CHECK)


class Entry:
    __slots__ = ("key", "label", "kind", "status", "scopes", "basis", "value",
                 "ladder", "note", "ruleset_id", "ruleset_version")

    def __init__(self, raw, ruleset_id, ruleset_version):
        self.key = raw.get("key") or ""
        self.label = raw.get("label") or ""
        self.kind = raw.get("kind") or "scalar"
        self.status = raw.get("status") or STATUS_PENDING
        self.scopes = tuple(raw.get("scopes") or ())
        self.basis = raw.get("basis") or {}
        self.value = raw.get("value", None)
        self.ladder = raw.get("ladder") or []
        self.note = raw.get("note") or ""
        self.ruleset_id = ruleset_id
        self.ruleset_version = ruleset_version
        if not self.key:
            raise RulesetError("规则条目缺少 key（ruleset=%s）" % ruleset_id)
        if self.status not in VALID_STATUS:
            raise RulesetError("规则条目 %s 的 status 非法: %r"
                               % (self.key, self.status))

    @property
    def verified(self):
        return self.status == STATUS_VERIFIED

    @property
    def has_value(self):
        if self.kind == "ladder":
            return bool(self.ladder)
        return self.value is not None

    def decimal(self):
        if self.value is None or isinstance(self.value, bool):
            return None
        if isinstance(self.value, Decimal):
            return self.value
        if isinstance(self.value, int):
            return Decimal(self.value)
        if isinstance(self.value, float):
            raise RulesetError("条目 %s 值落到 float，加载器 parse_float 失效" % self.key)
        try:
            return Decimal(str(self.value).strip())
        except Exception:
            return None

    def tiers(self):
        return list(self.ladder)


class Ruleset:
    def __init__(self, raw, expected_sha=None):
        if raw.get("schema") != SCHEMA_RULESET:
            raise RulesetError("ruleset schema 不符: %r" % (raw.get("schema"),))
        self.id = raw.get("id") or ""
        self.version = raw.get("version") or ""
        self.title = raw.get("title") or ""
        self.doc_no = raw.get("doc_no") or ""
        self.anchor_from = raw.get("anchor_from") or ""
        self.anchor_to = raw.get("anchor_to") or ""
        self.source = raw.get("source") or {}
        self.expected_sha256 = expected_sha
        if not self.id or not self.version:
            raise RulesetError("ruleset 缺少 id/version")
        self.entries = {}
        for item in raw.get("entries") or []:
            entry = Entry(item, self.id, self.version)
            if entry.key in self.entries:
                raise RulesetError("ruleset %s 条目 key 重复: %s" % (self.id, entry.key))
            self.entries[entry.key] = entry

    def anchor(self):
        return "%s@%s" % (self.id, self.version)

    def status_counts(self):
        counts = {s: 0 for s in VALID_STATUS}
        for entry in self.entries.values():
            counts[entry.status] = counts.get(entry.status, 0) + 1
        return counts

    def get(self, key):
        return self.entries.get(key)


class RuleLibrary:
    def __init__(self, manifest, rulesets, data_dir):
        if manifest.get("schema") != SCHEMA_MANIFEST:
            raise RulesetError("manifest schema 不符: %r" % (manifest.get("schema"),))
        self.raw_manifest = manifest
        self.data_dir = Path(data_dir)
        self.rulesets = {rs.id: rs for rs in rulesets}
        self.scopes = tuple(manifest.get("scopes") or ("calc",))
        self.benchmarks = manifest.get("benchmarks") or {}

    def ruleset(self, ruleset_id):
        try:
            return self.rulesets[ruleset_id]
        except KeyError:
            raise RulesetError("规则集不存在: %r（可用: %s）"
                               % (ruleset_id, ", ".join(sorted(self.rulesets))))

    def entry(self, key):
        for rs in self.rulesets.values():
            entry = rs.get(key)
            if entry is not None:
                return entry
        return None

    def entries_with_prefix(self, prefix):
        found = []
        for rs in self.rulesets.values():
            for key, entry in sorted(rs.entries.items()):
                if key.startswith(prefix):
                    found.append(entry)
        return found

    def status_counts(self):
        counts = {s: 0 for s in VALID_STATUS}
        for rs in self.rulesets.values():
            for status, n in rs.status_counts().items():
                counts[status] = counts.get(status, 0) + n
        return counts

    def coordinate(self):
        return {
            "manifest_schema": self.raw_manifest.get("schema"),
            "rulesets": [
                {"id": rs.id, "version": rs.version, "title": rs.title,
                 "doc_no": rs.doc_no, "anchor_from": rs.anchor_from,
                 "anchor_to": rs.anchor_to, "sha256": rs.expected_sha256,
                 "status_counts": rs.status_counts()}
                for rs in sorted(self.rulesets.values(), key=lambda r: r.id)
            ],
            "scope_gate": list(self.scopes),
        }

    def benchmark_threshold(self, suite):
        cfg = self.benchmarks.get(suite)
        if not cfg:
            raise RulesetError("manifest 未下发基准门槛: %s" % suite)
        return cfg


def _load_json(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RulesetError("规则文件不可读: %s (%s)" % (path, exc))
    try:
        return json.loads(text, parse_float=Decimal)
    except ValueError as exc:
        raise RulesetError("规则文件 JSON 非法: %s (%s)" % (path, exc))


def load_library(data_dir=None):
    root = Path(registry.DATA_DIR if data_dir is None else os.path.abspath(str(data_dir)))
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError("规则包 manifest 不存在: %s" % manifest_path)
    manifest = _load_json(manifest_path)
    rulesets = []
    for meta in manifest.get("rulesets") or []:
        fname = meta.get("file")
        if not fname:
            raise RulesetError("manifest 条目缺少 file: %r" % (meta.get("id"),))
        raw = _load_json(root / fname)
        if raw.get("id") != meta.get("id"):
            raise RulesetError("manifest 与 ruleset id 不一致: %r vs %r"
                               % (meta.get("id"), raw.get("id")))
        if raw.get("version") != meta.get("version"):
            raise RulesetError("manifest 与 ruleset version 不一致: %s %r vs %r"
                               % (meta.get("id"), meta.get("version"),
                                  raw.get("version")))
        rulesets.append(Ruleset(raw, expected_sha=meta.get("sha256")))
    return RuleLibrary(manifest, rulesets, root)


@dataclass
class GateDecision:
    scope: str
    allowed: bool
    blocked: list = field(default_factory=list)
    required_inputs: list = field(default_factory=list)
    permitted_unverified: list = field(default_factory=list)
    statuses: dict = field(default_factory=dict)

    @property
    def reasons(self):
        out = []
        for _, code in self.blocked:
            if code not in out:
                out.append(code)
        return tuple(out)


def evaluate(entries, scope, preview=False, provided_inputs=()):
    provided = set(provided_inputs)
    decision = GateDecision(scope=scope, allowed=True, statuses={})
    for entry in entries:
        if entry.scopes and scope not in entry.scopes:
            continue
        decision.statuses[entry.key] = entry.status
        if entry.status == STATUS_VERIFIED:
            if not entry.has_value:
                decision.blocked.append((entry.key, "missing_value"))
                decision.allowed = False
            continue
        if entry.status == STATUS_INPUT_REQUIRED:
            if entry.key not in provided:
                decision.required_inputs.append(entry.key)
            continue
        if entry.status == STATUS_PENDING:
            if preview:
                decision.permitted_unverified.append(entry.key)
            else:
                decision.blocked.append((entry.key, "gated_pending"))
                decision.allowed = False
            continue
        decision.blocked.append((entry.key, "gated_pending"))
        decision.allowed = False
    if decision.required_inputs:
        decision.allowed = False
    return decision


def evaluate_keys(library, keys, scope, preview=False, provided_inputs=()):
    entries = []
    missing = []
    for key in keys:
        entry = library.entry(key)
        if entry is None:
            missing.append((key, "untracked_entry"))
        else:
            entries.append(entry)
    decision = evaluate(entries, scope, preview=preview,
                        provided_inputs=provided_inputs)
    if missing:
        decision.blocked = missing + decision.blocked
        decision.allowed = False
    return decision


__all__ = ["MANIFEST_NAME", "STATUS_VERIFIED", "STATUS_PENDING",
           "STATUS_INPUT_REQUIRED", "VALID_STATUS", "SCOPE_CALC", "SCOPE_LATE",
           "SCOPE_REDUCTION", "SCOPE_CHECK", "ALL_SCOPES", "Entry", "Ruleset",
           "RuleLibrary", "load_library", "GateDecision", "evaluate",
           "evaluate_keys"]