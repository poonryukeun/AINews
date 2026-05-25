#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AINewsWebsite - 每日生成脚本（GitHub Actions 用）

输入：
  - sources.yml（RSS/Atom 源 + 简单主题规则）

输出（相对仓库根目录）：
  - docs/posts/YYYY-MM-DD.md
  - docs/posts/index.md
  - docs/topics/index.md
  - docs/topics/<主题>.md（如需要）
  - briefings/YYYY-MM-DD.raw.md（追溯用）
"""

from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import feedparser
import yaml
from dateutil import tz


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
POSTS_DIR = DOCS_DIR / "posts"
TOPICS_DIR = DOCS_DIR / "topics"
BRIEFINGS_DIR = ROOT / "briefings"


def now_in_tz(tz_name: str) -> dt.datetime:
    return dt.datetime.now(tz.gettz(tz_name))


def date_str(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def ensure_dirs() -> None:
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)


def slugify_anchor(text: str) -> str:
    # 生成稳定锚点：保留中文、英文数字；其它用 -
    s = text.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff\-]+", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:80] if s else "item"


def first_paragraph(html_or_text: str) -> str:
    # feedparser 的 summary 常含 HTML，做最小清洗
    t = re.sub(r"<[^>]+>", "", html_or_text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


@dataclass
class FeedSource:
    name: str
    url: str
    default_topics: list[str]


@dataclass
class NewsItem:
    title: str
    url: str
    published: dt.datetime | None
    source_name: str
    source_url: str
    summary: str
    topics: list[str]
    anchor: str


def load_config() -> dict[str, Any]:
    with (ROOT / "sources.yml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_datetime(entry: dict[str, Any]) -> dt.datetime | None:
    # feedparser 给 published_parsed/updated_parsed
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            return dt.datetime(*st[:6], tzinfo=dt.timezone.utc)
    return None


def within_window(published_utc: dt.datetime | None, now_utc: dt.datetime, hours: int = 36) -> bool:
    if not published_utc:
        return True  # 没有时间的条目先保留，后续可手动调整源
    delta = now_utc - published_utc
    return dt.timedelta(hours=0) <= delta <= dt.timedelta(hours=hours)


def apply_topic_rules(text: str, rules: list[dict[str, Any]]) -> list[str]:
    t = text.lower()
    hits: list[str] = []
    for r in rules:
        topic = str(r.get("topic", "")).strip()
        kws = r.get("keywords") or []
        for kw in kws:
            if str(kw).lower() in t:
                hits.append(topic)
                break
    # 去重保持顺序
    seen = set()
    out = []
    for x in hits:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def fetch_items(cfg: dict[str, Any]) -> list[NewsItem]:
    tz_name = cfg.get("timezone", "Asia/Shanghai")
    now_local = now_in_tz(tz_name)
    now_utc = now_local.astimezone(dt.timezone.utc)
    rules = cfg.get("topic_rules") or []

    items: list[NewsItem] = []
    for fs in cfg.get("feeds", []):
        src = FeedSource(
            name=str(fs["name"]),
            url=str(fs["url"]),
            default_topics=list(fs.get("default_topics") or []),
        )
        feed = feedparser.parse(src.url)
        for e in feed.entries or []:
            title = str(e.get("title", "")).strip()
            link = str(e.get("link", "")).strip()
            if not title or not link:
                continue

            published_utc = parse_datetime(e)
            if not within_window(published_utc, now_utc, hours=48):
                continue

            summary = first_paragraph(str(e.get("summary", "")) or str(e.get("description", "")) or "")
            text_for_topics = f"{title}\n{summary}"
            extra_topics = apply_topic_rules(text_for_topics, rules)
            topics = list(dict.fromkeys(src.default_topics + extra_topics))  # 保序去重
            anchor = slugify_anchor(title)

            items.append(
                NewsItem(
                    title=title,
                    url=link,
                    published=(published_utc.astimezone(tz.gettz(tz_name)) if published_utc else None),
                    source_name=src.name,
                    source_url=src.url,
                    summary=summary,
                    topics=topics or ["产品与应用"],
                    anchor=anchor,
                )
            )
    # 去重（按 URL）
    uniq: dict[str, NewsItem] = {}
    for it in items:
        uniq.setdefault(it.url, it)
    out = list(uniq.values())
    # 按发布时间倒序（无时间的放后）
    out.sort(key=lambda x: x.published or dt.datetime.min.replace(tzinfo=tz.gettz("Asia/Shanghai")), reverse=True)
    return out[:15]


def render_post(today: str, site_title: str, items: list[NewsItem]) -> str:
    # 代表性主题：取出现频率前 6
    freq: dict[str, int] = {}
    for it in items:
        for tpc in it.topics:
            freq[tpc] = freq.get(tpc, 0) + 1
    top_topics = [k for k, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))][:6] or ["产品与应用"]

    sources = []
    for it in items:
        sources.append({"name": it.source_name, "url": it.source_url})
    # 去重来源
    seen = set()
    sources2 = []
    for s in sources:
        key = (s["name"], s["url"])
        if key not in seen:
            sources2.append(s)
            seen.add(key)

    summary_line = "今日更新：RSS/公告源的新增条目已聚合并按主题整理。"
    if not items:
        summary_line = "今日可核实新增条目不足；已生成空模板以保证流水线稳定。"

    front = [
        "---",
        f'title: "每日 AI 资讯｜{today}"',
        f'date: "{today}"',
        f"topics: {top_topics}",
        "sources:",
    ]
    for s in sources2[:10]:
        front.append(f'  - name: "{s["name"]}"')
        front.append(f'    url: "{s["url"]}"')
    front += [f'summary: "{summary_line}"', "---", ""]

    lines = front
    lines += ["## 今日要点", ""]
    if items:
        for it in items[:6]:
            lines.append(f"- {it.title}（{it.source_name}）")
    else:
        lines.append("- （无可核实新增条目）")
    lines += ["", "## 主题速览", ""]

    # 按主题分组
    grouped: dict[str, list[NewsItem]] = {}
    for it in items:
        for tpc in it.topics:
            grouped.setdefault(tpc, []).append(it)
    for tpc in sorted(grouped.keys()):
        lines += [f"### {tpc}", ""]
        for it in grouped[tpc]:
            lines += [
                f'<a id="{it.anchor}"></a>',
                f"#### {it.title}",
                f"摘要：{it.summary or '（无摘要）'}",
                "关键点：",
                "- （待补充：可在后续版本加入更强的摘要/要点生成）",
                f"来源：[{it.source_name}]({it.url})",
                "",
            ]

    if items:
        lines += ["## 延伸阅读", ""]
        for it in items[:5]:
            lines.append(f"- [{it.title}]({it.url})")
        lines.append("")

    return "\n".join(lines)


def update_posts_index(today: str, post_filename: str) -> None:
    idx = POSTS_DIR / "index.md"
    content = idx.read_text(encoding="utf-8") if idx.exists() else "# 每日文章（索引）\n\n"

    # 插入到“最新文章”下方第一条
    new_line = f"- {today}｜[每日 AI 资讯｜{today}]({post_filename})"
    if new_line in content:
        return

    # 简单策略：找到“## 最新文章”后第一段，插入一行
    parts = content.splitlines()
    out: list[str] = []
    inserted = False
    for i, line in enumerate(parts):
        out.append(line)
        if not inserted and line.strip() == "## 最新文章":
            # 跳过空行后插入
            out.append("")
            out.append(new_line)
            inserted = True
    if not inserted:
        out += ["", "## 最新文章", "", new_line]

    # 归档：按 YYYY-MM
    ym = today[:7]
    archive_header = f"### {ym}"
    archive_line = f"- {today}｜[每日 AI 资讯｜{today}]({post_filename})"
    if archive_header not in "\n".join(out):
        out += ["", archive_header, "", archive_line]
    else:
        # 若已存在该月份，追加在月份段末尾
        out2: list[str] = []
        in_month = False
        month_added = False
        for line in out:
            if line.strip().startswith("### "):
                if in_month and not month_added:
                    out2.append(archive_line)
                    month_added = True
                in_month = (line.strip() == archive_header)
            out2.append(line)
        if in_month and not month_added:
            out2.append(archive_line)
        out = out2

    idx.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def topic_filename(topic: str) -> str:
    # 简单文件名清洗
    t = re.sub(r"[/:*?\"<>|]+", "", topic).strip()
    return f"{t}.md"


def ensure_topic_page(topic: str) -> Path:
    fp = TOPICS_DIR / topic_filename(topic)
    if not fp.exists():
        fp.write_text(f"# {topic}\n\n本页聚合与「{topic}」主题相关的每日条目。\n\n## 2026\n\n", encoding="utf-8")
    return fp


def update_topics(today: str, items: list[NewsItem]) -> None:
    # 更新 topics/index.md 与各主题页
    topics = sorted({t for it in items for t in it.topics})
    if not topics:
        topics = ["产品与应用"]

    # 主题页追加
    for tpc in topics:
        fp = ensure_topic_page(tpc)
        text = fp.read_text(encoding="utf-8")
        for it in [x for x in items if tpc in x.topics]:
            line = f"- {today}｜{it.title} → [查看](../posts/{today}.md#{it.anchor})"
            if line not in text:
                text = text.rstrip() + "\n" + line + "\n"
        fp.write_text(text, encoding="utf-8")

    # 更新索引页（只维护链接列表）
    idx = TOPICS_DIR / "index.md"
    header = "# 主题（索引）\n\n此页将由自动化任务根据每日文章的 `topics` 字段自动生成/更新。\n\n## 主题列表\n\n"
    body = "\n".join([f"- [{t}]({topic_filename(t)})" for t in topics]) + "\n"
    idx.write_text(header + body, encoding="utf-8")


def write_raw(today: str, items: list[NewsItem]) -> None:
    fp = BRIEFINGS_DIR / f"{today}.raw.md"
    lines = [
        f"# {today} 原始链接（追溯用）",
        "",
        "> 说明：由 RSS/Atom 源聚合得到，用于追溯与核查。",
        "",
    ]
    for it in items:
        lines += [
            f"- {it.title}",
            f"  - 来源：{it.source_name}",
            f"  - 链接：{it.url}",
        ]
    fp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    ensure_dirs()
    cfg = load_config()
    tz_name = cfg.get("timezone", "Asia/Shanghai")
    today = date_str(now_in_tz(tz_name).date())
    site_title = cfg.get("site_title", "AI 资讯博客")

    items = fetch_items(cfg)

    post_path = POSTS_DIR / f"{today}.md"
    post_path.write_text(render_post(today, site_title, items), encoding="utf-8")

    update_posts_index(today, f"{today}.md")
    update_topics(today, items)
    write_raw(today, items)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

