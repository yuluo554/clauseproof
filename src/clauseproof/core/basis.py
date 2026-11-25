"""条文库：条款锚点的唯一来源。

条文库按版本登记（编号 + 条款路径 + 生效/失效日期 + 来源）。器官只能通过
``Basis.anchor(clause_id)`` 拿锚点；拿不到就只能降级为 ``not_applicable``，
不许自己造条款。
"""

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from clauseproof.core.ledger import Anchor, ContractError


class BasisMissing(Exception):
    """条文库里没有这条款（或版本不符）。"""


@dataclass(frozen=True)
class Clause:
    """一条条文。"""

    clause_id: str
    path: str
    version: str
    text: str = ""
    effective: Optional[str] = None
    expires: Optional[str] = None

    def __post_init__(self) -> None:
        for name, value in (
            ("clause_id", self.clause_id),
            ("path", self.path),
            ("version", self.version),
        ):
            if value is None or not str(value).strip():
                raise ContractError("条款字段为空：%s" % name)

    def as_dict(self) -> dict:
        return {
            "clause_id": self.clause_id,
            "path": self.path,
            "version": self.version,
            "text": self.text,
            "effective": self.effective,
            "expires": self.expires,
        }


class Basis:
    """一个版本下的条文集合。

    ``version`` 是条文库版本（不是单条条文版本）；单条条款的版本必须与库版本一致，
    否则视为条文库自相矛盾（``ContractError``）。
    """

    def __init__(self, version: str, clauses: Iterable[Clause] = ()) -> None:
        if not version or not str(version).strip():
            raise ContractError("条文库版本为空")
        self._version = version
        self._clauses = {}
        for clause in clauses:
            if clause.version != version:
                raise ContractError(
                    "条款版本与条文库版本不符：%s(%s) != %s"
                    % (clause.clause_id, clause.version, version)
                )
            if clause.clause_id in self._clauses:
                raise ContractError("条款重复：%s" % clause.clause_id)
            self._clauses[clause.clause_id] = clause

    # ------------------------------------------------------------------ 构造
    @classmethod
    def empty(cls, version: str = "0") -> "Basis":
        return cls(version=version, clauses=())

    @classmethod
    def from_dict(cls, data: dict) -> "Basis":
        version = data.get("version")
        raw = data.get("clauses", [])
        if not isinstance(raw, list):
            raise ContractError("clauses 必须是数组")
        clauses = [
            Clause(
                clause_id=item.get("clause_id", ""),
                path=item.get("path", ""),
                version=item.get("version", version if isinstance(version, str) else ""),
                text=item.get("text", ""),
                effective=item.get("effective"),
                expires=item.get("expires"),
            )
            for item in raw
        ]
        return cls(version=version, clauses=clauses)

    @classmethod
    def from_json(cls, path: str) -> "Basis":
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    # ------------------------------------------------------------------ 查询
    @property
    def version(self) -> str:
        return self._version

    def __len__(self) -> int:
        return len(self._clauses)

    def clause_ids(self) -> List[str]:
        return sorted(self._clauses)

    def clause(self, clause_id: str) -> Optional[Clause]:
        return self._clauses.get(clause_id)

    def require(self, clause_id: str) -> Clause:
        clause = self.clause(clause_id)
        if clause is None:
            raise BasisMissing("条文库 %s 无此条款：%s" % (self._version, clause_id))
        return clause

    def anchor(self, clause_id: str) -> Anchor:
        """给器官用的唯一取锚点入口。"""
        clause = self.require(clause_id)
        return Anchor(
            clause_id=clause.clause_id,
            path=clause.path,
            version=clause.version,
            quote=clause.text,
        )

    def as_dict(self) -> Dict[str, object]:
        return {
            "version": self._version,
            "clauses": [self._clauses[key].as_dict() for key in sorted(self._clauses)],
        }