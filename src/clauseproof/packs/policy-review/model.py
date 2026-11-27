"""规则包数据模型（迁自来源 ``rules.FeatureRule`` / ``PatternRule`` / ``RulesPackage``）。

规则包 = 10 类模式 + 5 部依据（条文锚点）。模式声明的 ``severity_base`` /
``escalation`` / ``statute_anchors`` / ``background_anchors`` 是分级与锚点的唯一来源；
引擎源码零等级字面量（除 ``constants`` 的词汇表）。
"""


class FeatureRule(object):
    __slots__ = ("feature_id", "type", "value", "description", "regex")

    def __init__(self, feature_id, type_, value, description, regex):
        self.feature_id = feature_id
        self.type = type_
        self.value = value
        self.description = description
        self.regex = regex


class PatternRule(object):
    __slots__ = (
        "pattern_id", "name_zh", "severity_base", "needs_semantic",
        "trigger_features", "negation", "neutralizers", "escalation",
        "statute_anchors", "background_anchors", "evidence_date", "version",
    )

    def __init__(self, data, triggers, negations, neutralizers, escalation):
        self.pattern_id = data["pattern_id"]
        self.name_zh = data["name_zh"]
        self.severity_base = data["severity_base"]
        self.needs_semantic = bool(data["needs_semantic"])
        self.trigger_features = tuple(triggers)
        self.negation = tuple(negations)
        self.neutralizers = tuple(neutralizers)
        self.escalation = tuple(escalation)
        self.statute_anchors = tuple(data["statute_anchors"])
        self.background_anchors = tuple(data["background_anchors"])
        self.evidence_date = data["evidence_date"]
        self.version = data["version"]

    def as_dict(self):
        return {
            "pattern_id": self.pattern_id,
            "name_zh": self.name_zh,
            "severity_base": self.severity_base,
            "needs_semantic": self.needs_semantic,
            "trigger_features": [feature.feature_id
                                 for feature in self.trigger_features],
            "negation": [feature.feature_id for feature in self.negation],
            "neutralizers": [feature.feature_id for feature in self.neutralizers],
            "statute_anchors": list(self.statute_anchors),
            "background_anchors": list(self.background_anchors),
            "evidence_date": self.evidence_date,
            "version": self.version,
        }


class RulesPackage(object):
    """一份随包规则库（模式 + 锚点 + 坐标）。"""

    def __init__(self, manifest, patterns, anchors):
        self.manifest = manifest
        self.ruleset_version = str(manifest.get("ruleset_version", ""))
        self.patterns = tuple(patterns)
        self._pattern_map = {pattern.pattern_id: pattern for pattern in patterns}
        self.anchors = anchors

    def pattern(self, pattern_id):
        return self._pattern_map.get(pattern_id)

    def anchor(self, anchor_id):
        return self.anchors.get(anchor_id)

    @property
    def pending_anchors(self):
        return {anchor_id: anchor for anchor_id, anchor in self.anchors.items()
                if not anchor["eligible"]}

    def coordinate(self):
        hard = sum(1 for anchor in self.anchors.values() if anchor["eligible"])
        pending = len(self.anchors) - hard
        return {
            "ruleset_version": self.ruleset_version,
            "generated_on": self.manifest.get("generated_on", ""),
            "patterns": len(self.patterns),
            "statutes": len({anchor["statute_id"] for anchor in self.anchors.values()}),
            "anchors": len(self.anchors),
            "hard_anchors": hard,
            "pending_anchors": pending,
        }


__all__ = ["FeatureRule", "PatternRule", "RulesPackage"]