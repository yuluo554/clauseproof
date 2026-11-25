"""冻结规则表与字段映射表（**Python 字面量，零文件读取**）。

来源：迁自 target-map ① 行的冻结产物
``data/rules/{labeling-measures,gb45438-2025}/2025-09-01.json`` +
``data/mapping/national-fields.json``。

为什么把数据搬成字面量而不是运行时读 JSON：器官**不读文件**（执行约束）。
``data/`` 下仍逐字保存三份来源 JSON 作为**可复核的出处**——它们随 wheel 进包
（见 ``[tool.setuptools.package-data]``），并由 ``tests/test_labeling_claims.py``
的「漂移门」逐条比对"字面量 == 冻结产物"，两边不一致即红。

规则条目的 ``status`` 保留来源口径：只有 ``verified`` 进判定路径，``pending``
一律不判定（来源产品 NFR-4）。
"""

from typing import Any, Dict, Tuple

# 相对导入：目录名带连字符（= 器官 slug），包内引用一律用相对形态
from .engine import FieldMapping, Rule

# ---------------------------------------------------------------------------
# 条文库版本：本规则表核对时依据的条文库坐标（单一值，改版 = 整表重核）
# ---------------------------------------------------------------------------
BASIS_VERSION = "2025-09-01"

# ---------------------------------------------------------------------------
# 条文（clause_id → 路径 + 原文要点）
# ---------------------------------------------------------------------------
GB = "GB 45438-2025"
MEASURES = "《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号）"
GB_URL = "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=F32EA2A561F1886CD8D606513512D547"
MEASURES_URL = "https://www.gov.cn/zhengce/zhengceku/202503/content_7014286.htm"

#: ``(clause_id, path, text, source)``；``text`` 逐字取自冻结规则条目的 clause.excerpt。
CLAUSES: Tuple[Tuple[str, str, str, str], ...] = (
    ("gb45438:5.1:a", GB + "/5.1 a)",
     "文本内容显式标识应采用文字或角标形式并具备标识", GB_URL),
    ("gb45438:5.1:b1", GB + "/5.1 b) 1)",
     "文本内容显式标识应含人工智能要素：包含“人工智能”或“AI”", GB_URL),
    ("gb45438:5.1:b2", GB + "/5.1 b) 2)",
     "文本内容显式标识应含生成合成要素：包含“生成”和/或“合成”", GB_URL),
    ("gb45438:5.1:d", GB + "/5.1 d)",
     "文本内容显式标识应位于文本的起始位置、末尾位置或中间适当位置之一或多个", GB_URL),
    ("gb45438:5.2:a", GB + "/5.2 a)",
     "图片内容显式标识应采用文字提示并具备标识", GB_URL),
    ("gb45438:5.2:b1", GB + "/5.2 b) 1)",
     "图片内容显式标识应含人工智能要素：包含“人工智能”或“AI”", GB_URL),
    ("gb45438:5.2:b2", GB + "/5.2 b) 2)",
     "图片内容显式标识应含生成合成要素：包含“生成”和/或“合成”", GB_URL),
    ("gb45438:5.2:c", GB + "/5.2 c)",
     "图片内容显式标识应位于图片的边或角", GB_URL),
    ("gb45438:5.3:a", GB + "/5.3 a)",
     "音频内容显式标识应采用语音标识或音频节奏标识并具备标识", GB_URL),
    ("gb45438:5.3:b1", GB + "/5.3 b) 1)",
     "音频内容显式标识应含人工智能要素：包含“人工智能”或“AI”", GB_URL),
    ("gb45438:5.3:b2", GB + "/5.3 b) 2)",
     "音频内容显式标识应含生成合成要素：包含“生成”和/或“合成”", GB_URL),
    ("gb45438:5.3:d", GB + "/5.3 d)",
     "音频内容显式标识应位于音频的起始位置、末尾位置或中间适当位置之一或多个", GB_URL),
    ("gb45438:5.4:a", GB + "/5.4 a)",
     "视频内容显式标识应采用文字提示并具备标识", GB_URL),
    ("gb45438:5.4:b1", GB + "/5.4 b) 1)",
     "视频内容显式标识应含人工智能要素：包含“人工智能”或“AI”", GB_URL),
    ("gb45438:5.4:b2", GB + "/5.4 b) 2)",
     "视频内容显式标识应含生成合成要素：包含“生成”和/或“合成”", GB_URL),
    ("gb45438:5.4:c", GB + "/5.4 c)",
     "视频内容显式标识应位于视频起始画面，可位于视频末尾和中间适当位置", GB_URL),
    ("gb45438:6.1:a1", GB + "/6.1 a) 1)",
     "文件元数据隐式标识应包括生成合成标签要素：内容的人工智能生成合成属性信息", GB_URL),
    ("gb45438:6.1:a2", GB + "/6.1 a) 2)",
     "文件元数据隐式标识应包括生成合成服务提供者要素：生成合成服务提供者的名称或编码", GB_URL),
    ("gb45438:6.1:a3", GB + "/6.1 a) 3)",
     "文件元数据隐式标识应包括内容制作编号要素：生成合成服务提供者对该内容的唯一编号", GB_URL),
    ("gb45438:6.1:a4", GB + "/6.1 a) 4)",
     "文件元数据隐式标识应含内容传播服务提供者的名称或编码（传播场景适用）", GB_URL),
    ("gb45438:6.1:a5", GB + "/6.1 a) 5)",
     "文件元数据隐式标识应含内容传播服务提供者对该内容的唯一编号（传播场景适用）", GB_URL),
    ("gb45438:6.1:c", GB + "/6.1 c)",
     "文件元数据隐式标识应仅保留一份（同一标识要素不得重复提供）", GB_URL),
    ("gb45438:E:c1", GB + "/附录 E c) 1)",
     "生成合成标签要素（Label）取值：1=属于、2=可能为、3=疑似为人工智能生成合成内容", GB_URL),
    ("gb45438:E:d2", GB + "/附录 E d) 2)",
     "生成合成服务提供者要素（ContentProducer）类型为字符串", GB_URL),
    ("gb45438:E:e2", GB + "/附录 E e) 2)",
     "内容制作编号要素（ProduceID）类型为字符串", GB_URL),
    ("measures:4-2", MEASURES + "/第四条第二款",
     "提供下载、复制、导出等功能时，应确保文件中含有符合本办法第四条要求的显式标识（导出场景适用）",
     MEASURES_URL),
    ("measures:6", MEASURES + "/第六条",
     "提供网络信息内容传播服务的服务提供者应核验隐式标识，并在发布内容周边添加显著的提示标识（传播场景适用）",
     MEASURES_URL),
)

# ---------------------------------------------------------------------------
# 规则表
# 字段序：(rule_id, scope, carrier, target, check_type, params, severity,
#          scenarios, clause_id, status)
# ---------------------------------------------------------------------------
_AI_PATTERN: Dict[str, Any] = {"regex": ".*(人工智能|AI).*"}
_GEN_PATTERN: Dict[str, Any] = {"regex": ".*(生成|合成).*"}
_HEAD_MID_TAIL: Dict[str, Any] = {"allowed": ["head", "tail", "middle"]}

_RULES_RAW: Tuple[Tuple, ...] = (
    # --- 《标识办法》7 条 pending：条号已核对，技术判定由国标承担 ----
    ("measures:explicit:text.notice.position", "explicit", ("text",),
     "text_explicit_notice", "position", _HEAD_MID_TAIL, "minor", (), "", "pending"),
    ("measures:explicit:image.notice.presence", "explicit", ("image",),
     "image_explicit_notice", "presence", {}, "major", (), "", "pending"),
    ("measures:explicit:audio.notice.presence", "explicit", ("audio",),
     "audio_explicit_notice", "presence", {}, "major", (), "", "pending"),
    ("measures:explicit:video.notice.presence", "explicit", ("video",),
     "video_explicit_notice", "presence", {}, "major", (), "", "pending"),
    ("measures:implicit:content.property.presence", "implicit", (),
     "content_property", "presence", {}, "critical", (), "", "pending"),
    ("measures:implicit:service.provider.presence", "implicit", (),
     "content_producer", "presence", {}, "major", (), "", "pending"),
    ("measures:implicit:content.id.presence", "implicit", (),
     "content_id", "presence", {}, "minor", (), "", "pending"),
    # --- 《标识办法》2 条 verified：办法独有义务 ----
    ("measures:explicit:export.file.label.presence", "explicit", (),
     "exported_file_explicit_label", "presence", {}, "major",
     ("exported",), "measures:4-2", "verified"),
    ("measures:propagation:platform.hint.presence", "explicit", (),
     "propagation_platform_hint", "presence", {}, "major",
     ("propagated",), "measures:6", "verified"),
    # --- GB 45438-2025 §5.1 文本显式 ----
    ("gb45438:explicit:text.notice.presence", "explicit", ("text",),
     "text_explicit_notice", "presence", {}, "major", (), "gb45438:5.1:a", "verified"),
    ("gb45438:explicit:text.notice.position", "explicit", ("text",),
     "text_explicit_notice", "position", _HEAD_MID_TAIL, "minor", (),
     "gb45438:5.1:d", "verified"),
    ("gb45438:explicit:text.notice.ai_element", "explicit", ("text",),
     "text_explicit_notice", "pattern", _AI_PATTERN, "major", (),
     "gb45438:5.1:b1", "verified"),
    ("gb45438:explicit:text.notice.gen_element", "explicit", ("text",),
     "text_explicit_notice", "pattern", _GEN_PATTERN, "major", (),
     "gb45438:5.1:b2", "verified"),
    # --- §5.2 图片显式 ----
    ("gb45438:explicit:image.notice.presence", "explicit", ("image",),
     "image_explicit_notice", "presence", {}, "major", (), "gb45438:5.2:a", "verified"),
    ("gb45438:explicit:image.notice.position", "explicit", ("image",),
     "image_explicit_notice", "position", {"allowed": ["edge", "corner"]}, "minor", (),
     "gb45438:5.2:c", "verified"),
    ("gb45438:explicit:image.notice.ai_element", "explicit", ("image",),
     "image_explicit_notice", "pattern", _AI_PATTERN, "major", (),
     "gb45438:5.2:b1", "verified"),
    ("gb45438:explicit:image.notice.gen_element", "explicit", ("image",),
     "image_explicit_notice", "pattern", _GEN_PATTERN, "major", (),
     "gb45438:5.2:b2", "verified"),
    # --- §5.3 音频显式 ----
    ("gb45438:explicit:audio.notice.presence", "explicit", ("audio",),
     "audio_explicit_notice", "presence", {}, "major", (), "gb45438:5.3:a", "verified"),
    ("gb45438:explicit:audio.notice.position", "explicit", ("audio",),
     "audio_explicit_notice", "position", _HEAD_MID_TAIL, "minor", (),
     "gb45438:5.3:d", "verified"),
    ("gb45438:explicit:audio.notice.ai_element", "explicit", ("audio",),
     "audio_explicit_notice", "pattern", _AI_PATTERN, "major", (),
     "gb45438:5.3:b1", "verified"),
    ("gb45438:explicit:audio.notice.gen_element", "explicit", ("audio",),
     "audio_explicit_notice", "pattern", _GEN_PATTERN, "major", (),
     "gb45438:5.3:b2", "verified"),
    # --- §5.4 视频显式 ----
    ("gb45438:explicit:video.notice.presence", "explicit", ("video",),
     "video_explicit_notice", "presence", {}, "major", (), "gb45438:5.4:a", "verified"),
    ("gb45438:explicit:video.notice.position", "explicit", ("video",),
     "video_explicit_notice", "position", _HEAD_MID_TAIL, "minor", (),
     "gb45438:5.4:c", "verified"),
    ("gb45438:explicit:video.notice.ai_element", "explicit", ("video",),
     "video_explicit_notice", "pattern", _AI_PATTERN, "major", (),
     "gb45438:5.4:b1", "verified"),
    ("gb45438:explicit:video.notice.gen_element", "explicit", ("video",),
     "video_explicit_notice", "pattern", _GEN_PATTERN, "major", (),
     "gb45438:5.4:b2", "verified"),
    # --- §6.1 + 附录 E 隐式 ----
    ("gb45438:implicit:content_property.presence", "implicit", (),
     "content_property", "presence", {}, "critical", (), "gb45438:6.1:a1", "verified"),
    ("gb45438:implicit:content_property.enum", "implicit", (),
     "content_property", "enum", {"allowed": ["1", "2", "3"]}, "minor", (),
     "gb45438:E:c1", "verified"),
    ("gb45438:implicit:content_producer.presence", "implicit", (),
     "content_producer", "presence", {}, "major", (), "gb45438:6.1:a2", "verified"),
    ("gb45438:implicit:content_producer.type", "implicit", (),
     "content_producer", "type", {"expect": "string"}, "minor", (),
     "gb45438:E:d2", "verified"),
    ("gb45438:implicit:content_id.presence", "implicit", (),
     "content_id", "presence", {}, "minor", (), "gb45438:6.1:a3", "verified"),
    ("gb45438:implicit:content_id.type", "implicit", (),
     "content_id", "type", {"expect": "string"}, "minor", (), "gb45438:E:e2", "verified"),
    ("gb45438:implicit:implicit_label.uniqueness", "implicit", (),
     "content_property", "unique", {}, "major", (), "gb45438:6.1:c", "verified"),
    ("gb45438:implicit:content_propagator.presence", "implicit", (),
     "content_propagator", "presence", {}, "major", ("propagated",),
     "gb45438:6.1:a4", "verified"),
    ("gb45438:implicit:propagate_id.presence", "implicit", (),
     "propagate_id", "presence", {}, "minor", ("propagated",),
     "gb45438:6.1:a5", "verified"),
)

RULES: Tuple[Rule, ...] = tuple(Rule(*row) for row in _RULES_RAW)

#: 待核对条目（一律不进入判定路径；``evaluate`` 只把它们登记成一行 ``not_applicable``）
PENDING_RULE_IDS: Tuple[str, ...] = tuple(
    rule.rule_id for rule in RULES if not rule.is_effective)

#: 拿不到条文库时的兜底不需要——锚点只能来自 ``Basis``（器官不造条款）

# ---------------------------------------------------------------------------
# 字段映射表（国标字段 ← 容器键；aliases 声明序敏感）
# ---------------------------------------------------------------------------
FIELDS: Tuple[FieldMapping, ...] = (
    FieldMapping("content_property",
                 ("AIGC:Label", "AIGC.Label", "aigc.label", "Label")),
    FieldMapping("content_producer",
                 ("AIGC:ContentProducer", "AIGC.ContentProducer",
                  "aigc.contentproducer", "ContentProducer")),
    FieldMapping("content_id",
                 ("AIGC:ProduceID", "AIGC.ProduceID", "aigc.produceid", "ProduceID")),
    FieldMapping("content_propagator",
                 ("AIGC:ContentPropagator", "AIGC.ContentPropagator",
                  "aigc.contentpropagator", "ContentPropagator",
                  "AIGC:Propagator", "AIGC.Propagator",
                  "aigc.propagator", "Propagator")),
    FieldMapping("propagate_id",
                 ("AIGC:PropagateID", "AIGC.PropagateID",
                  "aigc.propagateid", "PropagateID",
                  "AIGC:PropagatorID", "AIGC.PropagatorID",
                  "aigc.propagatorid", "PropagatorID")),
)


def clause_ids() -> Tuple[str, ...]:
    """条文库应含的全部 clause_id（字典序）。"""
    return tuple(sorted(clause_id for clause_id, _p, _t, _s in CLAUSES))


__all__ = [
    "BASIS_VERSION", "CLAUSES", "RULES", "PENDING_RULE_IDS", "FIELDS", "clause_ids",
]