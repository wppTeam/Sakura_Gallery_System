"""轻量中文检索分词（与数据库 ``sakura_search_tokens()`` 保持一致）。

设计目标：**零第三方依赖**，在 2c4g 机器上也能跑；不引入 jieba（可选优化）。

规则：

- NFKC 归一化 + 小写
- 连续 CJK 段（汉字 / 假名 / 谚文）切成字符**二元组**，长度 1 保留单字
- 拉丁字母 / 数字段按单词保留
- 输出顺序去重、限制长度，空格连接后可直接交给 ``to_tsvector('simple', ...)``

查询侧用 :func:`build_or_tsquery` 生成 ``'樱花 | 花盛'`` 形式的 tsquery，
用 OR 保证召回，排序交给 ``ts_rank_cd`` 或应用层打分。
"""
from __future__ import annotations

import re
import unicodedata

CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+")
WORD_RE = re.compile(r"[A-Za-z0-9_]+")
MAX_TOKENS = 400


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def tokenize_for_search(text: str | None) -> list[str]:
    """把一段文本切成检索 token 列表（CJK 二元组 + 拉丁词）。"""
    normalized = _normalize(text or "")
    if not normalized.strip():
        return []

    tokens: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> bool:
        if not token or token in seen:
            return True
        seen.add(token)
        tokens.append(token)
        return len(tokens) < MAX_TOKENS

    for chunk in CJK_RE.findall(normalized):
        if len(chunk) == 1:
            if not add(chunk):
                return tokens
            continue
        for i in range(len(chunk) - 1):
            if not add(chunk[i : i + 2]):
                return tokens

    for word in WORD_RE.findall(normalized):
        if not add(word):
            return tokens

    return tokens


def search_tokens_text(text: str | None) -> str:
    """返回写入 ``photos.search_tokens`` 的空格分隔 token 串。"""
    return " ".join(tokenize_for_search(text))


def build_or_tsquery(text: str | None) -> str | None:
    """构造 ``'a | b | c'`` 形式的 tsquery 字符串；无 token 时返回 None。

    token 只含 CJK / 字母 / 数字 / 下划线，不含 tsquery 元字符，可直接拼接。
    """
    tokens = tokenize_for_search(text)
    if not tokens:
        return None
    return " | ".join(tokens)
