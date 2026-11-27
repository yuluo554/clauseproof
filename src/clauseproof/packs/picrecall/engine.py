"""相似截图分组判定内核（迁自来源 ``picrecall.dedupe`` 的判定子集）。

纪律：
- 只读：本模块没有任何删除/改名/写回用户文件的代码路径；
- pHash 阈值单一来源（输入/随包数据），不读环境、不读时钟；
- 分组确定性：单链聚类，成员与组顺序按 path 排序；
- 保留建议优先级：分辨率（宽×高）→ 文件大小 → mtime_ns → 路径字典序。
"""

RESUGGESTION_HEADER = (
    "group_id", "suggestion", "path", "phash", "file_size", "width",
    "height", "mtime_ns", "max_distance_to_rep",
)

DEFAULT_THRESHOLD = 8
DEFAULT_HASH_SIZE = 8


class ItemError(ValueError):
    """截图指纹条目不合法 → 器官入口按输入不合法处理。"""


def parse_phash(value):
    """十六进制 pHash → int；非 16 位十六进制即拒绝。"""
    if not isinstance(value, str):
        raise ItemError("phash 必须是十六进制字符串：%r" % (value,))
    text = value.strip().lower()
    if len(text) != 16:
        raise ItemError("phash 长度必须是 16 位十六进制（hash_size=8）：%r" % (value,))
    try:
        return int(text, 16)
    except ValueError:
        raise ItemError("phash 不是合法十六进制：%r" % (value,))


def _int_field(item, name, minimum=0):
    value = item.get(name)
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ItemError("%s 必须是整数：%r" % (name, value))
    if number < minimum:
        raise ItemError("%s 须 ≥ %d：%r" % (name, minimum, value))
    return number


def parse_items(raw):
    """校验截图指纹条目；返回规范化列表（按 path 排序）。"""
    if not isinstance(raw, list):
        raise ItemError("items 必须是数组")
    if not raw:
        raise ItemError("items 为空：无可分组对象")
    items = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ItemError("items[%d] 必须是对象" % idx)
        path = str(item.get("path") or "").strip()
        if not path:
            raise ItemError("items[%d].path 必填" % idx)
        items.append({
            "path": path,
            "phash": item["phash"] if "phash" in item else None,
            "hash_int": parse_phash(item.get("phash")),
            "width": _int_field(item, "width"),
            "height": _int_field(item, "height"),
            "size": _int_field(item, "size"),
            "mtime_ns": _int_field(item, "mtime_ns"),
        })
    items.sort(key=lambda x: x["path"])
    return items


def _hamming(a, b):
    """汉明距离（Python 3.8 无 int.bit_count，用 bin().count）。"""
    return bin(a ^ b).count("1")


def group_items(items, threshold=DEFAULT_THRESHOLD):
    """单链聚类（确定性）：路径序起点，距离 ≤ threshold 即并入。"""
    if not isinstance(threshold, int) or threshold < 0:
        raise ValueError("threshold 必须是非负整数：%r" % (threshold,))
    groups = []
    used = set()
    for i, anchor in enumerate(items):
        if i in used:
            continue
        members = [i]
        used.add(i)
        changed = True
        while changed:
            changed = False
            for j, candidate in enumerate(items):
                if j in used:
                    continue
                if any(_hamming(items[k]["hash_int"], candidate["hash_int"])
                       <= threshold for k in members):
                    members.append(j)
                    used.add(j)
                    changed = True
        if len(members) > 1:
            groups.append([items[k] for k in members])
    out = []
    for gid, members in enumerate(groups, start=1):
        rep = choose_representative(members)
        out.append({
            "group_id": gid,
            "representative": rep,
            "members": [
                {
                    "path": m["path"],
                    "phash": "%016x" % m["hash_int"],
                    "file_size": m["size"],
                    "width": m["width"],
                    "height": m["height"],
                    "mtime_ns": m["mtime_ns"],
                    "max_distance_to_rep": _hamming(rep["hash_int"], m["hash_int"]),
                }
                for m in members
            ],
        })
    return out


def choose_representative(members):
    """保留建议优先级：分辨率面积 → 文件大小 → mtime_ns → 路径字典序。"""
    def key(member):
        area = (member["width"] or 0) * (member["height"] or 0)
        return (-area, -member["size"], -member["mtime_ns"], member["path"])

    return sorted(members, key=key)[0]


def suggestion_rows(groups):
    rows = []
    for group in groups:
        rep_path = group["representative"]["path"]
        for member in sorted(group["members"], key=lambda x: x["path"]):
            rows.append((
                group["group_id"],
                "keep" if member["path"] == rep_path else "redundant",
                member["path"], member["phash"], member["file_size"],
                member["width"], member["height"], member["mtime_ns"],
                member["max_distance_to_rep"],
            ))
    return rows


__all__ = ["RESUGGESTION_HEADER", "DEFAULT_THRESHOLD", "DEFAULT_HASH_SIZE",
           "ItemError", "parse_phash", "parse_items", "group_items",
           "choose_representative", "suggestion_rows"]