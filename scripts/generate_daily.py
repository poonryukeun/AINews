#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AINewsWebsite - 每日生成脚本（GitHub Actions 用）

双模式抓取：
  1. RSS/Atom 源 → feedparser
  2. HTML 页面 → requests + BeautifulSoup

输出：
  - docs/posts/YYYY-MM-DD.md
  - docs/posts/index.md
  - docs/topics/index.md
  - docs/topics/<主题>.md
  - briefings/YYYY-MM-DD.raw.md
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import feedparser
import yaml
from dateutil import tz

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
POSTS_DIR = DOCS_DIR / "posts"
TOPICS_DIR = DOCS_DIR / "topics"
BRIEFINGS_DIR = ROOT / "briefings"
RUNS_DIR = BRIEFINGS_DIR / "_runs"

UA = "Mozilla/5.0 (compatible; AINewsBot/1.0; +https://github.com/poonryukeun/AINews)"


# ═══════════════════════════════════════════════════════════════════
#  近期重大新闻回退 — 当实时抓取全部失败时使用
#  这些条目由人工/工具提前确认并写入，保证每日至少有一定内容
# ═══════════════════════════════════════════════════════════════════
FALLBACK_ITEMS: list[dict[str, Any]] = [
    {
        "title": "OpenAI 发布 GPT-5.5，编码与知识工作性能大幅提升",
        "url": "https://openai.com/index/introducing-gpt-5-5/",
        "source_name": "OpenAI",
        "source_url": "https://openai.com/news/",
        "summary": "GPT-5.5 在 Terminal-Bench 2.0 上达到 82.7% 准确率，在编码、知识工作与科学研究方面显著超越 GPT-5.4。支持更高效的 agentic 工作流，Token 消耗更少。",
        "topics": ["大模型", "产品与应用"],
    },
    {
        "title": "Google I/O 2026 发布 Gemini 3.5 Flash、Gemini Omni 世界模型与 Spark 个人 AI 代理",
        "url": "https://mashable.com/tech/all-the-gemini-announcements-google-io-2026",
        "source_name": "Google",
        "source_url": "https://deepmind.google/",
        "summary": "Gemini 3.5 Flash 速度快 4 倍；Gemini Omni 为多模态世界模型；Gemini Spark 为个人 AI 代理，集成 Google 生态。",
        "topics": ["大模型", "多模态", "智能体Agent"],
    },
    {
        "title": "Anthropic 与 Google、Broadcom 达成多 GW 级 TPU 算力合作",
        "url": "https://www.anthropic.com/news/google-broadcom-partnership-compute",
        "source_name": "Anthropic",
        "source_url": "https://www.anthropic.com/news",
        "summary": "年化收入超 300 亿美元，超 1000 家企业客户年消费超 100 万美元。新算力预计 2027 年上线，集中在美部署。",
        "topics": ["芯片与算力", "大模型"],
    },
    {
        "title": "NVIDIA 发布 Rubin 平台，6 款新品重新定义 AI 超算",
        "url": "https://nvidianews.nvidia.com/news/rubin-platform-ai-supercomputer",
        "source_name": "NVIDIA",
        "source_url": "https://nvidianews.nvidia.com/",
        "summary": "Rubin 平台包括 Vera CPU、Rubin GPU、NVLink 6 等，推理 Token 成本降低 10 倍，训练 MoE 模型所需 GPU 减少 4 倍。上半年投产。",
        "topics": ["芯片与算力", "训练与推理优化"],
    },
    {
        "title": "Hugging Face 春季报告：开源 AI 生态中国崛起，用户达 1300 万",
        "url": "https://huggingface.co/blog/huggingface/state-of-os-hf-spring-2026",
        "source_name": "Hugging Face",
        "source_url": "https://huggingface.co/blog",
        "summary": "开源 AI 使用量几近翻倍，中国模型下载量超越美国占 41%，独立开发者份额升至 39%。Baidu 从零增长到 100+ 模型发布。",
        "topics": ["开源生态", "数据与评测"],
    },
    {
        "title": "Anthropic 发布 Claude Opus 4.7 与 Claude Design",
        "url": "https://www.anthropic.com/news/claude-opus-4-7",
        "source_name": "Anthropic",
        "source_url": "https://www.anthropic.com/news",
        "summary": "Opus 4.7 在编码、视觉和多步骤任务上有显著提升，支持更高分辨率图像理解。同时推出 Claude Design 视觉协作产品。",
        "topics": ["大模型", "产品与应用", "多模态"],
    },
    {
        "title": "OpenAI 发布 GPT-Rosalind 生命科学模型",
        "url": "https://openai.com/index/introducing-gpt-rosalind/",
        "source_name": "OpenAI",
        "source_url": "https://openai.com/",
        "summary": "专为药物发现、蛋白质工程和基因组学设计的推理模型。在 BixBench 上领先所有已公布模型，通过受信访问计划开放。",
        "topics": ["大模型", "产品与应用"],
    },
    {
        "title": "OpenAI 发布 ChatGPT Images 2.0 与 Privacy Filter",
        "url": "https://openai.com/index/introducing-chatgpt-images-2-0/",
        "source_name": "OpenAI",
        "source_url": "https://openai.com/",
        "summary": "ChatGPT Images 2.0 引入新一代图像生成模型，支持多语言文本渲染。Privacy Filter 为开源 PII 检测模型，F1 达 97.43%。",
        "topics": ["多模态", "安全与对齐"],
    },
    {
        "title": "Hugging Face Transformers v5.8.0 发布，新增 DeepSeek-V4 等多模型支持",
        "url": "https://github.com/huggingface/transformers/releases/tag/v5.8.0",
        "source_name": "Hugging Face",
        "source_url": "https://github.com/huggingface/transformers/releases",
        "summary": "新模型支持包括 DeepSeek-V4、Gemma 4 Assistant、Granite Speech Plus、EXAONE 4.5 等，改进 tokenizer 与 bug 修复。",
        "topics": ["开源生态"],
    },
    {
        "title": "Anthropic 宣布 Project Glasswing 网络安全计划",
        "url": "https://www.anthropic.com/glasswing",
        "source_name": "Anthropic",
        "source_url": "https://www.anthropic.com/news",
        "summary": "联合 AWS、Apple、Cisco、Google、Microsoft、NVIDIA 等巨头成立软件安全联盟，同时推出 Claude for Open Source 计划。",
        "topics": ["安全与对齐", "开源生态"],
    },
]

# ═══════════════════════════════════════════════════════════════════


def now_in_tz(tz_name: str) -> dt.datetime:
    return dt.datetime.now(tz.gettz(tz_name))


def date_str(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def slugify_anchor(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff\-]+", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:80] if s else "item"


def first_paragraph(html_or_text: str) -> str:
    t = re.sub(r"<[^>]+>", "", html_or_text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:300]


@dataclass
class NewsItem:
    title: str
    url: str
    published: dt.datetime | None = None
    source_name: str = ""
    source_url: str = ""
    summary: str = ""
    topics: list[str] = field(default_factory=list)
    anchor: str = ""


def load_config() -> dict[str, Any]:
    with (ROOT / "sources.yml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def fetch_from_rss(feed_cfg: dict) -> list[dict[str, Any]]:
    """从 RSS/Atom 源抓取条目"""
    url = feed_cfg["url"]
    try:
        f = feedparser.parse(url)
    except Exception as e:
        log(f"  RSS parse error for {url}: {e}")
        return []

    items = []
    now_utc = dt.datetime.now(dt.timezone.utc)
    for e in (f.entries or []):
        title = str(e.get("title", "")).strip()
        link = str(e.get("link", "") or e.get("guid", "")).strip()
        if not title or not link:
            continue
        # 检查时效性（48h 内）
        pub = None
        for k in ("published_parsed", "updated_parsed"):
            st = e.get(k)
            if st:
                pub = dt.datetime(*st[:6], tzinfo=dt.timezone.utc)
                break
        if pub and (now_utc - pub) > dt.timedelta(hours=48):
            continue

        summary = first_paragraph(str(e.get("summary", "")) or "")
        items.append({
            "title": title,
            "url": link,
            "summary": summary,
            "source_name": feed_cfg.get("name", ""),
            "source_url": url,
        })
    return items


def fetch_from_html(feed_cfg: dict) -> list[dict[str, Any]]:
    """从 HTML 页面抓取条目（使用 requests + BeautifulSoup）"""
    if requests is None or BeautifulSoup is None:
        log(f"  requests/BeautifulSoup not available, skipping HTML fetch for {feed_cfg['url']}")
        return []

    url = feed_cfg["url"]
    sel = feed_cfg.get("selectors", {})
    list_sel = sel.get("list", "a")
    title_field = sel.get("title", "text")
    link_field = sel.get("link", "href")

    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        log(f"  HTTP error for {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.select(list_sel)

    items = []
    seen_urls = set()
    for a in links[:20]:
        title = a.get_text(strip=True) if title_field == "text" else a.get(title_field, "")
        href = a.get(link_field, "")
        if not title or not href:
            continue
        # 补齐相对路径
        if href.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"
        if href in seen_urls:
            continue
        seen_urls.add(href)
        items.append({
            "title": title[:120],
            "url": href,
            "summary": "",
            "source_name": feed_cfg.get("name", ""),
            "source_url": url,
        })
    return items


def apply_topic_rules(text: str, rules: list[dict]) -> list[str]:
    t = text.lower()
    hits = []
    for r in rules:
        topic = str(r.get("topic", "")).strip()
        for kw in (r.get("keywords") or []):
            if str(kw).lower() in t:
                hits.append(topic)
                break
    seen = set()
    out = []
    for x in hits:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def fetch_all_items(cfg: dict) -> list[NewsItem]:
    """聚合并标准化所有来源的条目"""
    tz_name = cfg.get("timezone", "Asia/Shanghai")
    rules = cfg.get("topic_rules") or []

    raw_items: list[dict] = []

    for fc in (cfg.get("feeds") or []):
        mode = fc.get("mode", "rss")
        log(f"  Fetching: {fc.get('name')} ({mode})")
        if mode == "html":
            items = fetch_from_html(fc)
        else:
            items = fetch_from_rss(fc)
        raw_items.extend(items)

    log(f"  Raw items collected: {len(raw_items)}")

    # 转换为 NewsItem
    now_local = now_in_tz(tz_name)
    result: list[NewsItem] = []
    for it in raw_items:
        text_for_topics = f"{it.get('title', '')} {it.get('summary', '')}"
        extra_topics = apply_topic_rules(text_for_topics, rules)
        default_topics = [str(t) for t in (it.get("default_topics") or [])]
        all_topics = list(dict.fromkeys(default_topics + extra_topics))
        if not all_topics:
            all_topics = ["产品与应用"]

        result.append(NewsItem(
            title=it["title"],
            url=it["url"],
            source_name=it.get("source_name", ""),
            source_url=it.get("source_url", ""),
            summary=it.get("summary", ""),
            topics=all_topics,
            anchor=slugify_anchor(it["title"]),
        ))

    # 去重（按 URL）
    seen_urls = set()
    deduped = []
    for it in result:
        if it.url and it.url not in seen_urls:
            deduped.append(it)
            seen_urls.add(it.url)

    return deduped[:15]


def build_fallback_items(cfg: dict, rules: list) -> list[NewsItem]:
    """构建回退条目（当实时抓取结果不足时使用）"""
    now_local = now_in_tz(cfg.get("timezone", "Asia/Shanghai"))
    items: list[NewsItem] = []
    for fb in FALLBACK_ITEMS:
        t = f"{fb['title']} {fb['summary']}"
        extra = apply_topic_rules(t, rules)
        all_topics = list(dict.fromkeys(fb.get("topics", []) + extra))
        items.append(NewsItem(
            title=fb["title"],
            url=fb["url"],
            source_name=fb["source_name"],
            source_url=fb["source_url"],
            summary=fb["summary"],
            topics=all_topics or ["产品与应用"],
            anchor=slugify_anchor(fb["title"]),
        ))
    return items


def render_post(today: str, site_title: str, items: list[NewsItem], from_fallback: bool) -> str:
    freq: dict[str, int] = {}
    for it in items:
        for tpc in it.topics:
            freq[tpc] = freq.get(tpc, 0) + 1
    top_topics = [k for k, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))][:6] or ["产品与应用"]

    sources = []
    seen = set()
    for it in items:
        key = (it.source_name, it.source_url)
        if key not in seen:
            sources.append({"name": it.source_name, "url": it.source_url})
            seen.add(key)

    notice = ""
    if from_fallback:
        notice = "\n> ⚠️ 本文基于近期重要新闻整理，非实时抓取结果。实时 RSS/HTML 源将在后续运行中逐步完善。\n"

    summary_line = "今日 AI 资讯聚合。"
    if not items:
        summary_line = "今日可核实条目不足。"
    elif from_fallback:
        summary_line = "基于近期重要新闻整理。请关注后续实时更新。"

    lines = [
        "---",
        f'title: "每日 AI 资讯｜{today}"',
        f'date: "{today}"',
        f"topics: {top_topics}",
        "sources:",
    ]
    for s in sources[:10]:
        lines.append(f'  - name: "{s["name"]}"')
        lines.append(f'    url: "{s["url"]}"')
    lines += [f'summary: "{summary_line}"', "---", ""]
    lines += [notice, "## 今日要点", ""] if notice else ["## 今日要点", ""]

    if items:
        for it in items[:8]:
            lines.append(f"- {it.title}（{it.source_name}）")
    else:
        lines.append("- （无可核实新增条目）")
    lines += ["", "## 主题速览", ""]

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
    content = idx.read_text(encoding="utf-8") if idx.exists() else "# 每日文章（索引）\n\n## 最新文章\n\n"
    new_line = f"- {today}｜[每日 AI 资讯｜{today}]({post_filename})"
    if new_line in content:
        return
    parts = content.splitlines()
    out: list[str] = []
    inserted = False
    for i, line in enumerate(parts):
        out.append(line)
        if not inserted and line.strip() == "## 最新文章":
            out.append("")
            out.append(new_line)
            inserted = True
    if not inserted:
        out += ["", "## 最新文章", "", new_line]
    idx.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def topic_filename(topic: str) -> str:
    t = re.sub(r"[/:*?\"<>|]+", "", topic).strip()
    return f"{t}.md"


def ensure_topic_page(topic: str) -> Path:
    fp = TOPICS_DIR / topic_filename(topic)
    if not fp.exists():
        fp.write_text(f"# {topic}\n\n本页聚合与「{topic}」主题相关的每日条目。\n\n## 2026\n\n", encoding="utf-8")
    return fp


def update_topics(today: str, items: list[NewsItem]) -> None:
    topics = sorted({t for it in items for t in it.topics})
    if not topics:
        topics = ["产品与应用"]
    for tpc in topics:
        fp = ensure_topic_page(tpc)
        text = fp.read_text(encoding="utf-8")
        for it in [x for x in items if tpc in x.topics]:
            line = f"- {today}｜{it.title} → [查看](../posts/{today}.md#{it.anchor})"
            if line not in text:
                text = text.rstrip() + "\n" + line + "\n"
        fp.write_text(text, encoding="utf-8")
    idx = TOPICS_DIR / "index.md"
    header = "# 主题（索引）\n\n此页将由自动化任务根据每日文章的 `topics` 字段自动生成/更新。\n\n## 主题列表\n\n"
    body = "\n".join([f"- [{t}]({topic_filename(t)})" for t in topics]) + "\n"
    idx.write_text(header + body, encoding="utf-8")


def write_raw(today: str, items: list[NewsItem]) -> None:
    fp = BRIEFINGS_DIR / f"{today}.raw.md"
    lines = [f"# {today} 原始链接（追溯用）", ""]
    if not items:
        lines.append("（无实时抓取结果，使用内置回退条目）")
        lines.append("")
    for it in items:
        lines += [f"- {it.title}", f"  - 来源：{it.source_name}", f"  - 链接：{it.url}"]
    fp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_run_log(today: str, status: str, details: str) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fp = RUNS_DIR / f"{today}.log.md"
    lines = [
        f"# 运行日志：{today}",
        f"时间：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"状态：{status}",
        "",
        details,
        "",
    ]
    fp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    log(details)


def main() -> int:
    log("=" * 50)
    log("AINewsWebsite 每日生成开始")
    log("=" * 50)

    ensure_dirs()
    cfg = load_config()
    tz_name = cfg.get("timezone", "Asia/Shanghai")
    today = date_str(now_in_tz(tz_name).date())
    site_title = cfg.get("site_title", "AI 资讯博客")
    rules = cfg.get("topic_rules") or []

    log(f"日期：{today}")
    log(f"工作目录：{ROOT}")
    log(f"配置文件：{ROOT / 'sources.yml'}")

    # 第1步：实时抓取
    log("第1步：实时抓取信息源...")
    items = fetch_all_items(cfg)
    from_fallback = False

    # 第2步：如果实时抓取不足，使用内置回退
    if len(items) < 6:
        log(f"实时抓取仅 {len(items)} 条，不足 6 条，使用内置回退条目补充...")
        fallback = build_fallback_items(cfg, rules)
        # 合并去重
        existing_urls = {it.url for it in items}
        for fb in fallback:
            if fb.url not in existing_urls:
                items.append(fb)
                existing_urls.add(fb.url)
        from_fallback = True
        items = items[:15]

    log(f"最终条目数：{len(items)}（来源：{'内置回退' if from_fallback else '实时抓取'}）")

    # 第3步：生成当日文章
    post_path = POSTS_DIR / f"{today}.md"
    content = render_post(today, site_title, items, from_fallback)
    post_path.write_text(content, encoding="utf-8")
    log(f"写入文章：{post_path}")

    # 第4步：更新索引
    update_posts_index(today, f"{today}.md")
    log("更新文章索引")

    # 第5步：更新主题页
    update_topics(today, items)
    log("更新主题聚合页")

    # 第6步：写入追溯文件
    write_raw(today, items)
    log("写入追溯文件")

    # 第7步：运行日志
    status = "SUCCESS"
    details = f"今日生成完成。条目数：{len(items)}，来源：{'内置回退' if from_fallback else '实时抓取'}"
    write_run_log(today, status, details)

    log("=" * 50)
    log("生成完成")
    log("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
