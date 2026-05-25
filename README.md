# AI 资讯博客（自动更新）

这是一个用于承载「每日 AI 新闻简报」的静态博客仓库。目标是：每天自动生成/更新内容，并按主题聚合。

本站点使用 **MkDocs + Material**（高效、稳定、维护成本低）。

## 目录结构

- `mkdocs.yml`：站点配置
- `docs/`：站点内容根目录（MkDocs 默认）
  - `docs/posts/`：每日文章（按日期生成）
  - `docs/topics/`：主题聚合页（自动维护）
  - `docs/assets/`：图片等静态资源（可选）
- `briefings/`：每日简报的原始/中间产物（可选，用于追溯）
- `requirements.txt`：Python 依赖（MkDocs）

## 本地预览（推荐）

安装依赖：

```bash
python3 -m pip install -r requirements.txt --break-system-packages
```

启动预览：

```bash
mkdocs serve
```

构建静态站点：

```bash
mkdocs build
```

## 每日自动生成（推荐：GitHub Actions，无需本地定时器）

由于本地定时自动化环境可能无法直接写入你电脑上的仓库目录，仓库已内置 GitHub Actions 定时任务：

- `.github/workflows/generate-daily.yml`：每天北京时间 08:00（UTC 00:00）拉取 RSS/Atom 源，生成/更新：
  - `docs/posts/YYYY-MM-DD.md`
  - `docs/posts/index.md`
  - `docs/topics/index.md` 与 `docs/topics/*.md`
  - `briefings/YYYY-MM-DD.raw.md`
- `.github/workflows/deploy-mkdocs.yml`：当 main 分支有更新时，部署到 `gh-pages`（GitHub Pages）

你可以通过编辑 `sources.yml` 来增删信息源与主题规则。

## 文章格式（docs/posts）

建议每篇文章使用 Markdown + YAML Front Matter，例如：

```md
---
title: "每日 AI 资讯｜2026-05-25"
date: "2026-05-25"
topics: ["大模型", "产品发布", "开源"]
sources:
  - name: "OpenAI Blog"
    url: "https://example.com"
summary: "一句话摘要..."
---

## 今日要点
- ...

## 主题速览
### 大模型
- ...
```

命名约定：`docs/posts/YYYY-MM-DD.md`

## 主题聚合（docs/topics）

`docs/topics/` 下的每个主题页用于聚合历史文章中与该主题相关的条目。主题页命名建议：

- `topics/大模型.md`
- `topics/产品发布.md`
- `topics/开源.md`

（后续我会根据你的主题体系自动生成/更新这些文件。）

## 首页（docs/index.md）

首页用于展示最新文章与主题入口，后续将由自动化任务每日更新。
