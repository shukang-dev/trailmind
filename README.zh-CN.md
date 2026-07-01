# Trailmind

[English README](README.md)

Trailmind 是一个以 Markdown 为后端的项目跟踪器，也是面向 AI 代理交接的工具。它把项目状态保存在仓库中的普通文件里，让人类和 AI 代理都可以直接查看、评审、比较和更新工作内容，不依赖额外服务。

Trailmind 是一个洁净室开源实现。仓库内容应避免包含私有代码、私有样例、组织专属集成、内部服务名称或专有示例。

## 工作方式

Markdown 文件和 YAML frontmatter 是唯一事实来源。Project、Epic、Task、Issue 和 Milestone 都会作为可读的 `.md` 文件保存在 `projects/` 下；结构化字段写在 frontmatter 中，正文保留目标、范围、验收标准和上下文。

Trailmind 面向人类与 AI 代理协作。创建 Project 和 Epic 时会生成 `AGENTS.md` 协议文件，用来说明本地交接规则、所需上下文，以及代理在仓库中工作的安全边界。

## 快速开始

从源码安装 Trailmind：

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

创建一个演示仓库，并添加公开样例用户：

```sh
mkdir demo-trailmind
cd demo-trailmind
git init

trailmind roster add \
  --email alice@example.com \
  --shortname alice \
  --name "Alice Example" \
  --uid 123456

trailmind roster list
```

创建 Project、Epic 和 Task：

```sh
trailmind project init \
  --slug demo_app \
  --title "Demo App" \
  --goal "Build a useful demo." \
  --owners alice@example.com \
  --tags demo,agent

trailmind epic init \
  --project demo_app \
  --slug mvp \
  --title "MVP" \
  --goal "First usable release" \
  --start 2026-06-29 \
  --target 2026-07-15 \
  --roster alice \
  --repos demo_app

trailmind task add \
  --epic projects/demo_app/mvp \
  --filer alice@example.com \
  --owner alice@example.com \
  --title "Build Login Flow" \
  --code-paths "src/app.py,tests/test_app.py"
```

更新工作、生成仪表盘，并启动本地服务：

```sh
trailmind log T-123456-001 --author alice --note "Started implementation."
trailmind task update T-123456-001 --status in_progress

trailmind status --overview
trailmind status --project demo_app
trailmind status --epic projects/demo_app/mvp

trailmind serve --host 127.0.0.1 --port 8888
```

可选的 Issue 和 Milestone 记录：

```sh
trailmind issue add \
  --epic projects/demo_app/mvp \
  --filer alice@example.com \
  --title "Login Fails" \
  --description "Users cannot sign in." \
  --severity high

trailmind issue link --issue I-123456-001 --task T-123456-001

trailmind milestone add \
  --epic projects/demo_app/mvp \
  --title "Beta Freeze" \
  --date 2026-07-15
```

运行发布扫描：

```sh
trailmind scan
```

## 项目自动化

Trailmind v0.2 提供任务状态流转、依赖、交付物、收件箱分诊和 sweep 报告等工作流辅助能力。详见
[v0.2 Project Automation 指南](docs/v0.2-project-automation.md)。

```sh
trailmind task add \
  --epic projects/demo_app/mvp \
  --filer alice@example.com \
  --owner alice@example.com \
  --title "Build Sign-In Form" \
  --depends-on T-123456-001 \
  --soft-depends-on T-123456-002 \
  --known-issues I-123456-001 \
  --deliverables "tests pass,docs updated"

trailmind task set-status T-123456-003 ready --actor alice --note "Ready to start."
trailmind task normalize-statuses
trailmind task normalize-statuses --write

trailmind task deliverable add T-123456-003 --item "docs updated" --actor alice
trailmind task deliverable complete T-123456-003 --item "docs updated" --actor alice

trailmind inbox add --epic projects/demo_app/mvp --author alice --title "Review release checklist" --note "Confirm before release."
trailmind inbox list --epic projects/demo_app/mvp
trailmind inbox resolve IN-20260630-001 --resolver alice --note "Filed a follow-up task."

trailmind sweep --epic projects/demo_app/mvp
```

## Agent 交接

Trailmind 可以为 Task 或 Issue 生成有边界的 pickup 上下文：

```sh
trailmind task pickup T-123456-001
trailmind task pickup T-123456-001 --json
trailmind issue pickup I-123456-001
trailmind issue pickup I-123456-001 --log --actor alice
```

Pickup 默认只读。完整说明见 `docs/v0.3-agent-handoff.md`。

## 主要功能

- 用 Markdown 存储 Project、Epic、Task、Issue 和 Milestone。
- 用 YAML frontmatter 保存结构化状态，用 Markdown 正文保存上下文。
- 在被跟踪记录中追加 Activity Log，形成持久历史。
- 通过 `depends_on`、`soft_depends_on` 和关联 Issue 表达任务依赖。
- 为 overview、project 和 epic 作用域生成 HTML 仪表盘。
- 通过 `trailmind serve` 启动本地仪表盘服务。
- 库级 Git 安全辅助函数，只暂存和提交指定路径。
- 发布扫描会检查非 example.com 邮箱、敏感环境文件、疑似令牌文本和被阻止的发布标记。
- 生成 `AGENTS.md` 协议文件，支持人类与 AI 代理交接。

## 许可证

Trailmind 使用 [MIT License](LICENSE) 发布。
