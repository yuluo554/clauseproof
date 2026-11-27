"""参数库：地区主数据、地区×年度规则包、全国法定常数包（迁自来源 ``params``）。

坐标精确匹配：``load_ruleset(region_code, year)`` 只按精确坐标命中，不做模糊/回退；
文件名与内部坐标必须一致（跨地区/跨年度混用在机制上不可能发生）。
数据目录定位收敛为**随包固定目录**（来源的环境变量/冻结态/上溯链留输入层）。
"""

import os
import re

from . import registry
from .decimalutil import load_json_decimal, to_decimal
from .errors import ParamCoordinateError, ParamSchemaError

RULES_FILENAME_RE = re.compile(r"^ruleset-(?P<region>[0-9A-Za-z]+)-(?P<year>\d{4})\.json$")

STATUS_PENDING = "pending"
STATUS_VERIFIED = "verified"
_VALID_STATUS = (STATUS_PENDING, STATUS_VERIFIED)

REQUIRED_SOURCE_KEYS = ("publisher", "published_year", "url", "retrieved_at")


class ParamEntry:
    __slots__ = ("path", "raw")

    def __init__(self, path, raw):
        self.path = path
        self.raw = raw

    @property
    def status(self):
        return str(self.raw.get("status", STATUS_PENDING))

    @property
    def is_verified(self):
        return self.status == STATUS_VERIFIED

    @property
    def unit(self):
        return self.raw.get("unit")

    @property
    def source(self):
        return dict(self.raw.get("source") or {})

    @property
    def basis(self):
        return list(self.raw.get("basis") or [])

    def value(self):
        raw = self.raw.get("value")
        if isinstance(raw, (list, dict, bool)):
            return raw
        return to_decimal(raw, self.path)


class Ruleset:
    def __init__(self, raw, source_file=None):
        self.raw = raw
        self.source_file = source_file

    @property
    def region_code(self):
        return str(self.raw.get("region_code", ""))

    @property
    def region_name(self):
        return str(self.raw.get("region_name", ""))

    @property
    def year(self):
        return int(self.raw.get("year", 0))

    @property
    def status(self):
        declared = str(self.raw.get("status", STATUS_PENDING))
        if declared != STATUS_VERIFIED:
            return STATUS_PENDING
        for entry in self.entries().values():
            if not entry.is_verified:
                return STATUS_PENDING
        return STATUS_VERIFIED

    @property
    def coordinate(self):
        return (self.region_code, self.year)

    def entries(self):
        result = {}
        for name, raw in (self.raw.get("params") or {}).items():
            path = "params.%s" % name
            if isinstance(raw, dict):
                result[path] = ParamEntry(path, raw)
        return result

    def get(self, name):
        entries = self.entries()
        key = "params.%s" % name
        if key not in entries:
            raise ParamSchemaError("参数包 %s 缺少条目 %s" % (self.coordinate, key))
        return entries[key]

    def _calendar(self, key):
        calendar = (self.raw.get("params") or {}).get("holiday_calendar") or {}
        return list(calendar.get(key) or [])

    def holiday_days(self):
        return self._calendar("days")

    def rest_days(self):
        return self._calendar("rest_days")

    def adjusted_workdays(self):
        return self._calendar("adjusted_workdays")

    def holiday_day_type(self, day):
        if day in self.holiday_days():
            return "statutory_holiday"
        if day in self.rest_days():
            return "rest_day"
        if day in self.adjusted_workdays():
            return "adjusted_workday"
        return "workday"


class Constants:
    def __init__(self, raw, source_file=None):
        self.raw = raw
        self.source_file = source_file

    @property
    def status(self):
        for entry in self.entries().values():
            if not entry.is_verified:
                return STATUS_PENDING
        return STATUS_VERIFIED

    def entries(self):
        result = {}

        def walk(prefix, node):
            if isinstance(node, dict):
                if "status" in node:
                    result[prefix] = ParamEntry(prefix, node)
                    return
                for key, child in node.items():
                    walk("%s.%s" % (prefix, key) if prefix else key, child)
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    walk("%s[%d]" % (prefix, index), child)

        for key, node in (self.raw.get("constants") or {}).items():
            walk(key, node)
        return result

    def get(self, path):
        entries = self.entries()
        if path not in entries:
            raise ParamSchemaError("常数包缺少条目 %s" % path)
        return entries[path]


class Regions:
    def __init__(self, raw, source_file=None):
        self.raw = raw
        self.source_file = source_file

    @property
    def regions(self):
        return list(self.raw.get("regions") or [])

    def codes(self):
        return [str(item.get("code")) for item in self.regions]

    def get(self, code):
        for item in self.regions:
            if str(item.get("code")) == str(code):
                return dict(item)
        raise ParamCoordinateError("地区码 %s 不在地区主数据中" % code)


def _root(data_dir):
    if data_dir is None:
        return registry.DATA_DIR
    path = os.path.abspath(str(data_dir))
    if not os.path.isdir(path):
        raise FileNotFoundError("指定的数据目录不可用: %s" % data_dir)
    return path


def _rules_dir(data_dir):
    return _root(data_dir)


def list_ruleset_files(data_dir=None):
    directory = _rules_dir(data_dir)
    if not os.path.isdir(directory):
        return []
    names = sorted(name for name in os.listdir(directory)
                   if RULES_FILENAME_RE.match(name))
    return [os.path.join(directory, name) for name in names]


def load_ruleset(region_code, year, data_dir=None, validate=True):
    try:
        year_int = int(year)
    except (TypeError, ValueError):
        raise ParamCoordinateError("年度非法: %r" % (year,))
    filename = "ruleset-%s-%d.json" % (region_code, year_int)
    path = os.path.join(_rules_dir(data_dir), filename)
    if not os.path.isfile(path):
        available = [os.path.basename(item) for item in list_ruleset_files(data_dir)]
        raise ParamCoordinateError(
            "无坐标 (%s, %d) 对应的参数包（期望文件 %s）。可用规则包: %s"
            % (region_code, year_int, filename, ", ".join(available) or "（无）")
        )
    ruleset = Ruleset(load_json_decimal(path), source_file=path)
    if validate:
        validate_ruleset(ruleset)
    return ruleset


def load_constants(data_dir=None, validate=True):
    path = os.path.join(_root(data_dir), "constants.json")
    if not os.path.isfile(path):
        raise ParamSchemaError("缺少法定常数包: %s" % path)
    constants = Constants(load_json_decimal(path), source_file=path)
    if validate:
        validate_constants(constants)
    return constants


def load_regions(data_dir=None, validate=True):
    path = os.path.join(_root(data_dir), "regions.json")
    if not os.path.isfile(path):
        raise ParamSchemaError("缺少地区主数据: %s" % path)
    regions = Regions(load_json_decimal(path), source_file=path)
    if validate:
        validate_regions(regions)
    return regions


def _check_status(entry, problems):
    if entry.status not in _VALID_STATUS:
        problems.append("%s: status 非法 %r" % (entry.path, entry.status))


def _check_source(entry, required_keys, problems, label="来源"):
    if not entry.is_verified:
        return
    source = entry.raw.get("source")
    if not isinstance(source, dict):
        problems.append("%s: status=verified 但缺少 %s 字段" % (entry.path, label))
        return
    for key in required_keys:
        if not source.get(key):
            problems.append("%s: status=verified 但 %s 缺字段 %r"
                            % (entry.path, label, key))


def validate_ruleset(ruleset, expected_region=None, expected_year=None):
    problems = []
    raw = ruleset.raw
    if not ruleset.region_code:
        problems.append("缺少 region_code")
    if not ruleset.year:
        problems.append("缺少 year")
    if raw.get("schema_version") is None:
        problems.append("缺少 schema_version")
    params = raw.get("params")
    if not isinstance(params, dict) or not params:
        problems.append("缺少 params")
    else:
        for name in ("social_avg_wage_monthly", "min_wage_monthly", "holiday_calendar"):
            if name not in params:
                problems.append("params 缺少必需条目 %r" % name)
    if ruleset.source_file:
        match = RULES_FILENAME_RE.match(os.path.basename(ruleset.source_file))
        if not match:
            problems.append("文件名不符合 ruleset-<region>-<year>.json: %s"
                            % os.path.basename(ruleset.source_file))
        else:
            if match.group("region") != ruleset.region_code:
                problems.append("文件名地区码 %r 与内部 region_code %r 不一致"
                                % (match.group("region"), ruleset.region_code))
            if int(match.group("year")) != ruleset.year:
                problems.append("文件名年度 %r 与内部 year %d 不一致"
                                % (match.group("year"), ruleset.year))
    if expected_region is not None and str(expected_region) != ruleset.region_code:
        problems.append("请求地区 %r 与参数包 region_code %r 不一致"
                        % (expected_region, ruleset.region_code))
    if expected_year is not None and int(expected_year) != ruleset.year:
        problems.append("请求年度 %r 与参数包 year %d 不一致"
                        % (expected_year, ruleset.year))
    for entry in ruleset.entries().values():
        _check_status(entry, problems)
        _check_source(entry, REQUIRED_SOURCE_KEYS, problems)
    if problems:
        raise ParamSchemaError(
            "参数包校验失败（%s）" % (ruleset.coordinate or "未知坐标",), problems)
    return ruleset


def validate_constants(constants):
    problems = []
    entries = constants.entries()
    if not entries:
        problems.append("常数包为空")
    for entry in entries.values():
        _check_status(entry, problems)
        if not entry.is_verified:
            continue
        if not entry.basis:
            problems.append("%s: status=verified 但缺 basis（条款依据）" % entry.path)
        if not entry.source.get("channel"):
            problems.append("%s: status=verified 但缺 source.channel" % entry.path)
    if problems:
        raise ParamSchemaError("法定常数包校验失败", problems)
    return constants


def validate_regions(regions):
    problems = []
    if not regions.regions:
        problems.append("地区主数据为空")
    seen = set()
    for item in regions.regions:
        code = str(item.get("code") or "")
        if not code:
            problems.append("地区条目缺 code")
            continue
        if code in seen:
            problems.append("地区码重复: %s" % code)
        seen.add(code)
        if not item.get("name"):
            problems.append("%s: 缺 name" % code)
        if not item.get("avg_wage_caliber"):
            problems.append("%s: 缺 avg_wage_caliber（口径登记为必填）" % code)
        if item.get("status") not in _VALID_STATUS:
            problems.append("%s: status 非法 %r" % (code, item.get("status")))
    if problems:
        raise ParamSchemaError("地区主数据校验失败", problems)
    return regions


def summarize(data_dir=None):
    root = _root(data_dir)
    summary = {"data_dir": root, "rulesets": [], "constants_status": None, "regions": []}
    for path in list_ruleset_files(data_dir):
        match = RULES_FILENAME_RE.match(os.path.basename(path))
        raw = load_json_decimal(path)
        summary["rulesets"].append({
            "file": os.path.basename(path),
            "region_code": str(raw.get("region_code", match.group("region"))),
            "region_name": str(raw.get("region_name", "")),
            "year": int(raw.get("year", match.group("year"))),
            "status": str(raw.get("status", STATUS_PENDING)),
        })
    try:
        summary["constants_status"] = load_constants(data_dir, validate=False).status
    except ParamSchemaError:
        summary["constants_status"] = None
    try:
        regions = load_regions(data_dir, validate=False)
        summary["regions"] = [
            {"code": str(item.get("code")), "name": str(item.get("name")),
             "caliber": str(item.get("avg_wage_caliber")),
             "status": str(item.get("status"))}
            for item in regions.regions
        ]
    except ParamSchemaError:
        summary["regions"] = []
    return summary


__all__ = ["RULES_FILENAME_RE", "STATUS_PENDING", "STATUS_VERIFIED",
           "REQUIRED_SOURCE_KEYS", "ParamEntry", "Ruleset", "Constants", "Regions",
           "list_ruleset_files", "load_ruleset", "load_constants", "load_regions",
           "validate_ruleset", "validate_constants", "validate_regions", "summarize"]