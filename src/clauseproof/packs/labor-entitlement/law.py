"""法条条款库（迁自来源 ``law``）：加载 + 依据解析。

呈现纪律：以「法律名 + 条号 + 要点」形式呈现；``points`` 为要点摘述，非全文转载。
依据联动：引擎结果只携带条款 id 列表；判定账本最终经 ``Basis.anchor(id)`` 取锚点。
"""

import os

from . import registry
from .decimalutil import load_json_decimal
from .errors import LawBasisError, ParamSchemaError

STATUS_PENDING = "pending"
STATUS_VERIFIED = "verified"


class Clause:
    __slots__ = ("raw",)

    def __init__(self, raw):
        self.raw = raw

    @property
    def id(self):
        return str(self.raw.get("id", ""))

    @property
    def law(self):
        return str(self.raw.get("law", ""))

    @property
    def article(self):
        return str(self.raw.get("article", ""))

    @property
    def title(self):
        return str(self.raw.get("title", ""))

    @property
    def points(self):
        return list(self.raw.get("points") or [])

    @property
    def status(self):
        return str(self.raw.get("status", STATUS_PENDING))

    @property
    def source(self):
        return dict(self.raw.get("source") or {})

    @property
    def citation(self):
        if self.article:
            return "《%s》%s" % (self.law, self.article)
        return "《%s》" % self.law

    def as_dict(self):
        return {
            "id": self.id,
            "law": self.law,
            "article": self.article,
            "title": self.title,
            "points": self.points,
            "status": self.status,
            "citation": self.citation,
            "source": self.source,
        }


class ClauseLibrary:
    def __init__(self, raw, source_file=None):
        self.raw = raw
        self.source_file = source_file
        self._index = {}
        for item in raw.get("clauses") or []:
            clause = Clause(item)
            if clause.id:
                self._index[clause.id] = clause

    def ids(self):
        return sorted(self._index)

    def clauses(self):
        return [self._index[key] for key in self.ids()]

    def has(self, clause_id):
        return clause_id in self._index

    def get(self, clause_id):
        if clause_id not in self._index:
            raise LawBasisError(
                "条款 id %r 不在条款库中（依据不得悬挂）" % (clause_id,),
                ["可用条款: %s" % (", ".join(self.ids()) or "（空）")],
            )
        return self._index[clause_id]

    def resolve(self, clause_ids):
        return [self.get(str(item)) for item in clause_ids]

    def pending_ids(self):
        return [clause.id for clause in self.clauses()
                if clause.status != STATUS_VERIFIED]


def load_library(data_dir=None, validate=True):
    root = registry.DATA_DIR if data_dir is None else os.path.abspath(str(data_dir))
    path = os.path.join(root, "law-clauses.json")
    if not os.path.isfile(path):
        raise ParamSchemaError("缺少条款库: %s" % path)
    library = ClauseLibrary(load_json_decimal(path), source_file=path)
    if validate:
        validate_library(library)
    return library


def validate_library(library):
    problems = []
    if not library.ids():
        problems.append("条款库为空")
    for clause in library.clauses():
        if not clause.law:
            problems.append("%s: 缺 law" % (clause.id or "<无 id>"))
        if not clause.article:
            problems.append("%s: 缺 article" % (clause.id or "<无 id>"))
        if clause.status == STATUS_VERIFIED and not clause.source.get("channel"):
            problems.append("%s: status=verified 但缺 source.channel" % clause.id)
        if not clause.points:
            problems.append("%s: 缺 points" % (clause.id or "<无 id>"))
        elif clause.status == STATUS_VERIFIED:
            for point in clause.points:
                if len(point) < 4:
                    problems.append("%s: 要点过短 %r" % (clause.id, point))
    if problems:
        raise ParamSchemaError("条款库校验失败", problems)
    return library


__all__ = ["STATUS_PENDING", "STATUS_VERIFIED", "Clause", "ClauseLibrary",
           "load_library", "validate_library"]