"""规则包加载与校验（迁自来源 ``rules``，K7 单点语义）。

随包目录 = 器官 ``data/``：10 份模式文件（``pattern-p01.json`` … ``pattern-p10.json``）
+ 5 份依据文件（``statute-<SID>.json``）+ 器官 ``manifest.json``。

**文件完整性是装配的一部分**：manifest 登记每个数据文件的 bytes / sha256，
失配即 ``RulesPackageError``（不拿被篡改的规则包做判定）。任何缺字段、坏正则、
无法解析的锚点、背景/硬锚点冲突都会聚合为一次错误，不静默跳过。
"""

import hashlib
import json
import os
import re

from . import registry
from .constants import (ARTICLE_STATUSES, BACKGROUND_PREFIX, EXPECTED_PATTERN_IDS,
                        GRADABLE_KINDS, HIT_KINDS, LEVELS)
from .errors import RulesPackageError
from .model import FeatureRule, PatternRule, RulesPackage

MANIFEST_NAME = "manifest.json"
SCHEMA_MANIFEST = "policy.rules.manifest/v1"

REQUIRED_PATTERN_FIELDS = (
    "pattern_id", "name_zh", "severity_base", "needs_semantic",
    "trigger_features", "negation", "neutralizers", "escalation",
    "statute_anchors", "background_anchors", "evidence_date", "version",
)
REQUIRED_FEATURE_FIELDS = ("feature_id", "type", "value")
REQUIRED_STATUTE_FIELDS = (
    "statute_id", "title", "source_url", "verified_on", "version",
    "article_count", "articles",
)
REQUIRED_ARTICLE_FIELDS = ("article", "anchor_id", "anchor_text", "status")


def pattern_file(pattern_id):
    return "pattern-%s.json" % pattern_id.lower()


def statute_file(statute_id):
    return "statute-%s.json" % statute_id


def _read_json(path, errors, label):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        errors.append("%s 无法读取：%s" % (label, exc))
    except ValueError as exc:
        errors.append("%s 无法解析：%s" % (label, exc))
    return None


def _check_file(directory, name, record, errors):
    expected_sha = (record or {}).get("sha256")
    expected_bytes = (record or {}).get("bytes")
    path = os.path.join(directory, name)
    if not expected_sha or expected_bytes is None:
        errors.append("manifest 的 %s 条目缺 sha256/bytes" % name)
        return None
    if not os.path.isfile(path):
        errors.append("manifest 登记的文件不存在：%s" % name)
        return None
    with open(path, "rb") as handle:
        raw = handle.read()
    if len(raw) != expected_bytes:
        errors.append("%s 字节数失配：%d != %d" % (name, len(raw), expected_bytes))
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        errors.append("%s sha256 失配" % name)
    return path


def _load_statutes(directory, manifest, errors):
    """返回 ``anchor_id -> 锚点记录``（含 ``eligible`` 标记）。"""
    anchors = {}
    for statute_id in manifest.get("statutes") or []:
        name = statute_file(statute_id)
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            errors.append("依据文件不存在：%s" % name)
            continue
        data = _read_json(path, errors, name)
        if not isinstance(data, dict):
            continue
        for field in REQUIRED_STATUTE_FIELDS:
            if field not in data:
                errors.append("%s 缺字段 %s" % (name, field))
        sid = data.get("statute_id")
        if sid != statute_id:
            errors.append("%s statute_id 与 manifest 不一致：%s" % (name, sid))
        if not str(data.get("title", "")).strip():
            errors.append("%s title 为空" % name)
        source_url = str(data.get("source_url", ""))
        if not source_url.startswith("http"):
            errors.append("%s source_url 非法" % name)
        verified_on = str(data.get("verified_on", ""))
        if not verified_on:
            errors.append("%s verified_on 为空" % name)
        if not str(data.get("version", "")).strip():
            errors.append("%s version 为空" % name)

        articles = data.get("articles")
        if not isinstance(articles, list) or not articles:
            errors.append("%s articles 必须是非空列表" % name)
            continue
        if data.get("article_count") != len(articles):
            errors.append("%s article_count 与实际条数不一致" % name)
        for article in articles:
            if not isinstance(article, dict):
                errors.append("%s 条款不是对象" % name)
                continue
            for field in REQUIRED_ARTICLE_FIELDS:
                if field not in article:
                    errors.append("%s 条款缺字段 %s" % (name, field))
            anchor_id = article.get("anchor_id")
            if not anchor_id:
                errors.append("%s 条款 anchor_id 为空" % name)
                continue
            expected = "%s-%s" % (sid, article.get("article", ""))
            if anchor_id != expected:
                errors.append("%s anchor_id 与 statute/article 不一致：%s != %s"
                              % (name, anchor_id, expected))
            if anchor_id in anchors:
                errors.append("%s anchor_id 重复：%s" % (name, anchor_id))
            status = article.get("status")
            if status not in ARTICLE_STATUSES:
                errors.append("%s 条款 status 非法：%s" % (name, status))
            text = article.get("anchor_text")
            if not isinstance(text, str) or not text.strip():
                errors.append("%s anchor_text 为空（%s）" % (name, anchor_id))
            eligible = bool(
                status == "verified" and isinstance(text, str) and text.strip()
                and source_url and verified_on
            )
            anchors[anchor_id] = {
                "anchor_id": anchor_id,
                "statute_id": sid,
                "article": str(article.get("article", "")),
                "anchor_text": text if isinstance(text, str) else "",
                "source_url": source_url,
                "verified_on": verified_on,
                "status": status,
                "eligible": eligible,
            }
    return anchors


def _compile_features(raw_features, label, pattern_id, errors):
    features = []
    seen = set()
    if raw_features is None:
        return features
    if not isinstance(raw_features, list):
        errors.append("%s %s 必须是列表" % (pattern_id, label))
        return features
    for feature in raw_features:
        if not isinstance(feature, dict):
            errors.append("%s %s 条目不是对象" % (pattern_id, label))
            continue
        for field in REQUIRED_FEATURE_FIELDS:
            if field not in feature:
                errors.append("%s %s 条目缺字段 %s" % (pattern_id, label, field))
        feature_id = feature.get("feature_id")
        if feature_id in seen:
            errors.append("%s %s feature_id 重复：%s" % (pattern_id, label, feature_id))
        seen.add(feature_id)
        if feature.get("type") != "regex":
            errors.append("%s %s 只支持 regex 类型：%s"
                          % (pattern_id, label, feature.get("type")))
            continue
        value = feature.get("value")
        if not isinstance(value, str) or not value:
            errors.append("%s %s 正则为空（%s）" % (pattern_id, label, feature_id))
            continue
        try:
            compiled = re.compile(value)
        except re.error as exc:
            errors.append("%s %s 正则编译失败（%s）：%s"
                          % (pattern_id, label, feature_id, exc))
            continue
        features.append(FeatureRule(feature_id, feature.get("type"), value,
                                    feature.get("description", ""), compiled))
    return features


def _validate_escalation(raw, pattern_id, errors):
    rules = []
    if raw is None:
        return rules
    if not isinstance(raw, list):
        errors.append("%s escalation 必须是列表" % pattern_id)
        return rules
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            errors.append("%s escalation 条目不是对象" % pattern_id)
            continue
        level = item.get("level")
        if level not in LEVELS:
            errors.append("%s escalation level 非法：%s" % (pattern_id, level))
            continue
        has_single = "pattern_id" in item
        has_multi = "pattern_ids" in item
        if has_single == has_multi:
            errors.append("%s escalation 必须且只能提供 pattern_id 或 pattern_ids"
                          % pattern_id)
            continue
        refs = [item.get("pattern_id")] if has_single else item.get("pattern_ids")
        if not isinstance(refs, list) or not refs:
            errors.append("%s escalation pattern_ids 必须是非空列表" % pattern_id)
            continue
        unknown = [ref for ref in refs if ref not in EXPECTED_PATTERN_IDS]
        if unknown:
            errors.append("%s escalation 引用了未知模式：%s"
                          % (pattern_id, ", ".join(str(ref) for ref in unknown)))
            continue
        if pattern_id in refs:
            errors.append("%s escalation 不得引用自身" % pattern_id)
            continue
        key = (level, tuple(refs))
        if key in seen:
            errors.append("%s escalation 条目重复" % pattern_id)
            continue
        seen.add(key)
        normalized = {"level": level}
        if has_single:
            normalized["pattern_id"] = refs[0]
        else:
            normalized["pattern_ids"] = list(refs)
        rules.append(normalized)
    return rules


def _load_patterns(directory, manifest, anchors, errors):
    patterns = []
    ruleset_version = str(manifest.get("ruleset_version", ""))
    for pattern_id in manifest.get("patterns") or []:
        name = pattern_file(pattern_id)
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            errors.append("模式文件不存在：%s" % name)
            continue
        data = _read_json(path, errors, name)
        if not isinstance(data, dict):
            continue
        for field in REQUIRED_PATTERN_FIELDS:
            if field not in data:
                errors.append("%s 缺字段 %s" % (name, field))
        if data.get("pattern_id") != pattern_id:
            errors.append("%s pattern_id 与 manifest 不一致：%s"
                          % (name, data.get("pattern_id")))
        if data.get("severity_base") not in LEVELS:
            errors.append("%s severity_base 非法" % name)
        if not str(data.get("evidence_date", "")).strip():
            errors.append("%s evidence_date 为空" % name)
        if not str(data.get("version", "")).strip():
            errors.append("%s version 为空" % name)
        elif ruleset_version and data.get("version") != ruleset_version:
            errors.append("%s version 与 ruleset_version 不一致：%s vs %s"
                          % (name, data.get("version"), ruleset_version))
        if not isinstance(data.get("needs_semantic"), bool):
            errors.append("%s needs_semantic 必须是布尔值" % name)
        escalation = _validate_escalation(data.get("escalation"), pattern_id, errors)

        triggers = _compile_features(data.get("trigger_features"), "trigger_features",
                                     pattern_id, errors)
        if not triggers:
            errors.append("%s trigger_features 为空或全部无效" % name)
        negations = _compile_features(data.get("negation"), "negation",
                                      pattern_id, errors)
        neutralizers = _compile_features(data.get("neutralizers"), "neutralizers",
                                         pattern_id, errors)

        hard = data.get("statute_anchors")
        background = data.get("background_anchors")
        if not isinstance(hard, list):
            errors.append("%s statute_anchors 必须是列表" % name)
            hard = []
        if not isinstance(background, list):
            errors.append("%s background_anchors 必须是列表" % name)
            background = []
        for anchor_id in hard:
            if anchor_id not in anchors:
                errors.append("%s 硬锚点无法解析：%s" % (name, anchor_id))
        for anchor_id in background:
            if not str(anchor_id).startswith(BACKGROUND_PREFIX):
                errors.append("%s 背景锚点必须以 %s 开头：%s"
                              % (name, BACKGROUND_PREFIX, anchor_id))
            if anchor_id in hard:
                errors.append("%s 锚点同时出现在硬锚点与背景锚点：%s"
                              % (name, anchor_id))
        if not hard and data.get("severity_base") != "notice":
            errors.append("%s 无硬锚点但 severity_base != notice" % name)

        if all(field in data for field in REQUIRED_PATTERN_FIELDS):
            patterns.append(PatternRule(data, triggers, negations, neutralizers,
                                        escalation))
    return patterns


def load_library(data_dir=None):
    """定位、校验并加载规则包；任何问题抛 ``RulesPackageError``。"""
    directory = data_dir or registry.data_dir()
    errors = []
    manifest_path = os.path.join(directory, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        raise RulesPackageError("规则包缺失：%s 无 manifest.json" % directory)
    manifest = _read_json(manifest_path, errors, MANIFEST_NAME)
    if not isinstance(manifest, dict):
        raise RulesPackageError("规则包 manifest 顶层必须是对象")
    if manifest.get("schema") != SCHEMA_MANIFEST:
        raise RulesPackageError("规则包 manifest schema 不符：%r"
                                % manifest.get("schema"))
    if not str(manifest.get("ruleset_version", "")).strip():
        errors.append("manifest 的 ruleset_version 为空")
    if not str(manifest.get("version", "")).strip():
        errors.append("manifest 的 version 为空")

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RulesPackageError("规则包 manifest 的 files 必须是非空对象")
    for name, record in files.items():
        _check_file(directory, name, record, errors)

    patterns_ids = manifest.get("patterns")
    if list(patterns_ids or []) != list(EXPECTED_PATTERN_IDS):
        errors.append("manifest 的 patterns 必须恰为 P01–P10：%r" % (patterns_ids,))
    statutes_ids = manifest.get("statutes")
    if not isinstance(statutes_ids, list) or not statutes_ids:
        errors.append("manifest 的 statutes 必须是非空列表")

    anchors = _load_statutes(directory, manifest, errors)
    patterns = _load_patterns(directory, manifest, anchors, errors)
    if errors:
        raise RulesPackageError("规则包校验失败（%d 项）：\n  - %s"
                                % (len(errors), "\n  - ".join(errors)))
    return RulesPackage(manifest, patterns, anchors)


__all__ = ["MANIFEST_NAME", "SCHEMA_MANIFEST", "REQUIRED_PATTERN_FIELDS",
           "REQUIRED_FEATURE_FIELDS", "REQUIRED_STATUTE_FIELDS",
           "REQUIRED_ARTICLE_FIELDS", "pattern_file", "statute_file",
           "load_library"]