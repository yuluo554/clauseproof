"""规则包 manifest：年度→版本锚定 + 逐文件指纹校验（迁自来源 ``rules.manifest``）。

``rules-manifest.json`` 是**规则包坐标与指纹的唯一来源**（来源文件逐字节随包）：

* ``rulesets[]`` 登记每条规则的文号、生效年度区间、status 与三个文件的 sha256；
* 本器官把 ``<dir>/ruleset.json`` 等平铺为 ``ruleset-<版本>.json`` 等，
  **指纹仍按来源 manifest 逐文件核对**（规则包被手改即 ``IntegrityError``）；
* 年度锚定取该年 **1 月 1 日**：无匹配 → 退出码 2；多匹配 → 配置错误。
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from .errors import (AmbiguousRuleset, IntegrityError, NoRulesetForYear,
                     SchemaError)

SUPPORTED_SCHEMA_VERSION = 1

MANIFEST_FILE = "rules-manifest.json"
UNITS_FILE = "units.json"

# 来源目录 → 平铺文件后缀（按 ruleset_id 里的年份段推导）
def version_of(ruleset_id: str) -> str:
    parts = str(ruleset_id).split("-")
    if len(parts) < 2 or not parts[1].isdigit():
        raise SchemaError("无法从 ruleset_id 推导版本年度：%r" % ruleset_id)
    return parts[1]


def flat_name(kind: str, version: str) -> str:
    return "%s-%s.json" % (kind, version)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_day(value) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise SchemaError("日期字段应为 ISO 字符串：%r" % (value,))
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise SchemaError("日期字段不是 ISO 格式（YYYY-MM-DD）：%r" % (value,))


@dataclass(frozen=True)
class RulesetRef:
    ruleset_id: str
    version: str
    directory: str
    doc_no: str
    doc_title: str
    effective_from: date
    effective_to: Optional[date]
    status: str
    files: dict

    def covers(self, day: date) -> bool:
        if day < self.effective_from:
            return False
        return self.effective_to is None or day <= self.effective_to

    def as_dict(self) -> dict:
        return {
            "ruleset_id": self.ruleset_id,
            "version": self.version,
            "doc_no": self.doc_no,
            "doc_title": self.doc_title,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "status": self.status,
        }


class Manifest:
    def __init__(self, data_dir: str, payload: dict) -> None:
        if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
            raise SchemaError("rules-manifest schema_version 非法：%r"
                              % payload.get("schema_version"))
        self.data_dir = data_dir
        self._raw = payload
        self._refs: List[RulesetRef] = []
        for item in payload.get("rulesets", []):
            try:
                from_day = _parse_day(item["effective_from"])
                to_day = _parse_day(item["effective_to"]) if item.get("effective_to") else None
                ruleset_id = item["ruleset_id"]
                self._refs.append(RulesetRef(
                    ruleset_id=ruleset_id,
                    version=version_of(ruleset_id),
                    directory=item["dir"],
                    doc_no=item["doc_no"],
                    doc_title=item.get("doc_title", ""),
                    effective_from=from_day,
                    effective_to=to_day,
                    status=item.get("status", "pending"),
                    files=dict(item.get("files") or {}),
                ))
            except KeyError as exc:
                raise SchemaError("rules-manifest rulesets 条目缺字段：%s" % exc)

    @property
    def refs(self) -> Tuple[RulesetRef, ...]:
        return tuple(self._refs)

    @property
    def next_review(self) -> str:
        return str(self._raw.get("next_review", ""))

    @property
    def review_interval(self) -> str:
        return str(self._raw.get("review_interval", ""))

    def resolve(self, day: date) -> RulesetRef:
        matched = [ref for ref in self._refs if ref.covers(day)]
        if not matched:
            raise NoRulesetForYear("年度 %s 没有适用的规则集版本" % day.isoformat())
        if len(matched) > 1:
            raise AmbiguousRuleset("时点 %s 匹配到多个规则集：%s"
                                   % (day.isoformat(),
                                      ", ".join(ref.ruleset_id for ref in matched)))
        return matched[0]

    def resolve_year(self, year: int) -> RulesetRef:
        return self.resolve(date(int(year), 1, 1))

    def verify_integrity(self) -> None:
        """逐份校验规则文件 sha256（按来源 manifest 的 ``dir/file`` 登记值）。"""
        for ref in self._refs:
            for rel, expected in ref.files.items():
                kind = rel.split(".")[0]
                path = os.path.join(self.data_dir, flat_name(kind, ref.version))
                if not os.path.isfile(path):
                    raise IntegrityError("rules-manifest 登记的规则文件缺失：%s" % path)
                actual = sha256_file(path)
                if actual != expected:
                    raise IntegrityError(
                        "规则文件指纹不符（规则包被手改？）：%s 期望 %s 实际 %s"
                        % (path, expected, actual))


def build_manifest(data_dir: str, payload: dict) -> Manifest:
    return Manifest(data_dir, payload)


def load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise SchemaError("无法读取 %s：%s" % (path, exc))
    except ValueError as exc:
        raise SchemaError("%s 不是合法 JSON：%s" % (path, exc))


__all__ = ["SUPPORTED_SCHEMA_VERSION", "MANIFEST_FILE", "UNITS_FILE",
           "version_of", "flat_name", "sha256_file", "RulesetRef", "Manifest",
           "build_manifest", "load_json"]