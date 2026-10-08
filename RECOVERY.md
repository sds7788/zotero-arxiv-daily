# 每日论文推荐恢复记录（2026-10-08）

## 已确认的原因

1. 工作流 `212837801` / `.github/workflows/main.yml` 的公开 API 状态为 `disabled_inactivity`。这是停止定时触发的直接原因。
2. 最后一次运行 `21608577264` 的检查注释为：`The job was not acquired by Runner of type hosted even after multiple attempts`。任务没有分配到 runner，`runner_id=0`，执行步骤为空；因此这次失败没有执行到依赖安装、Zotero、LLM 或 SMTP 阶段。
3. 最后成功运行是 `21571324224`（2026-02-01）。最近 5 次运行列表中，最后一次失败之后没有新运行。
4. 失败运行从创建到结束约 15 分钟，不能据此归因于脚本达到 GitHub 托管任务的 6 小时上限。

GitHub 官方规则：公开仓库连续 60 天无活动时，定时工作流会被自动禁用。成功运行本身不会解决该限制。

- [GitHub 定时事件规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [重新启用工作流](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)

## 依赖与配置检查

- `.python-version` 为 Python 3.11。
- 原 uv 版本为 0.5.4；使用这个版本和 Python 3.11 执行 `uv lock --locked --offline` 已通过。
- 保留 `pyproject.toml` 和 `uv.lock` 的现有版本：arxiv 2.1.3、pyzotero 1.5.25、OpenAI 1.57.0、sentence-transformers 3.3.1、torch 2.5.1、llama-cpp-python 0.3.2。
- 没有证据表明这些版本导致最后一次失败。没有执行完整的 torch/llama 依赖安装或真实模型推理；runner 上的完整安装仍需干跑验证。
- 旧工作流允许 `REPOSITORY` / `REF` 变量改变实际执行的代码来源。修复后固定 checkout 当前仓库的运行提交，确保本仓库修复生效。这两个变量现在不再影响工作流。
- 仓库级 Actions 权限设置的公开 API 返回 401；现有插件没有提供该管理接口。该设置尚未通过认证检查。
- 未查询 Secrets 值，也未触发任何线上工作流或实际邮件。

## 本次修复

- 工作流使用 checkout v6、setup-python v6、setup-uv v7，明确安装 Python 3.11；uv 仍固定 0.5.4。
- 安装与运行分开，安装用 `uv sync --locked`，运行用 `uv run --no-sync`；开启 uv 依赖缓存。
- 安装限时 30 分钟、脚本限时 300 分钟、整个 job 限时 350 分钟。保留现有推荐数量配置，给本地 CPU LLM 留出时间。
- 两个工作流共用并发组，避免同时推理或发信；不自动重试 SMTP，减少重复邮件风险。
- arXiv RSS/API、源码下载、Papers With Code、OpenAI、SMTP 增加或明确超时。pyzotero 1.5.25 自身已有 30 秒请求超时。
- 对源码 503、代码链接查询失败、LLM 初始化失败、机构解析失败、摘要生成失败进行降级，尽可能继续提供论文与原摘要。Zotero 或 arXiv 主数据获取失败仍使任务失败，避免假成功。
- 修正命令行布尔值解析；`--use_llm_api false`、`--send_empty false` 不再被当成 true。
- SMTP 465 直接使用 SSL；其他标准 SMTP 端口使用 STARTTLS。自定义 SSL 端口需要另行适配。
- 每日工作流手动触发默认 `dry_run=true`。此时不向脚本传入 SMTP Secrets，并在发信调用之前返回。
- 测试工作流固定取最近 5 篇 cs.AI 论文，始终干跑，不含 SMTP Secrets；`--debug` 本身不提供发信保护，保护来自 `DRY_RUN=true` 和 `--dry_run`。

## 已完成的本地验证

```bash
python -m unittest discover -s tests -v
python -m py_compile main.py paper.py llm.py network.py construct_email.py tests/test_recovery.py
uv lock --locked --offline
actionlint .github/workflows/main.yml .github/workflows/test.yml
```

工作流通过 actionlint 1.7.12 检查。10 项离线回归测试通过，包括：完整模拟 5 篇论文的检索、排序、渲染及干跑流程；不配置 SMTP 也能干跑；干跑不调用 SMTP；网络超时；无效 RSS 不能伪装成无论文；源码 503、代码链接失败、LLM 初始化/推理失败降级；465/587 协议选择。测试采用假凭据和模拟模型/网络/SMTP，没有发送邮件。

另外，以公开 `cs.AI` 分类请求真实 RSS，返回 HTTP 200、Atom 解析正常、447 个条目。该检查不使用 Zotero 凭据，不执行模型和邮件流程。

## 授权后的恢复步骤

以下命令在已登录且有仓库管理权限的 GitHub CLI 中执行。不需要展示任何 Secrets，也不要在日志中打印环境变量。

### 1. 合并修复，核查仓库 Actions 设置

先审核并合并修复 PR。不要在修复合并前直接重跑旧 `test.yml`，旧测试工作流会发送邮件。

```bash
gh api repos/sds7788/zotero-arxiv-daily/actions/permissions \
  --jq '{enabled, allowed_actions}'
gh api repos/sds7788/zotero-arxiv-daily/actions/workflows/main.yml \
  --jq '{id, name, state}'
```

若 Actions 被整体禁用，在仓库 Settings → Actions → General 中启用；若仅允许指定 actions，要允许本工作流引用的三个官方 actions。检查 Secrets 时只核对名称是否存在，不取值、不重设、不复制到聊天或日志。

### 2. 先验证最近 5 篇论文，不发送邮件

```bash
gh workflow run test.yml --repo sds7788/zotero-arxiv-daily --ref main
gh run list --repo sds7788/zotero-arxiv-daily \
  --workflow test.yml --event workflow_dispatch --limit 3
# 将下方 RUN_ID 替换为本次新运行 ID
gh run watch RUN_ID --repo sds7788/zotero-arxiv-daily --exit-status
```

验收：依赖安装成功；Zotero 有可用摘要；取到并排序 5 篇样本；完成邮件渲染；末尾出现 `Dry run complete: recommendation email rendered; SMTP was not contacted.`。

干跑会使用配置好的 Zotero API 和模型，也可能产生 LLM API 费用；不会连接 SMTP。推荐正文和完整 Zotero 内容不打印到日志。

### 3. 重新启用每日工作流，再验证当天数据

重新启用会恢复真正的每日邮件，应先获得用户确认。

```bash
gh workflow enable main.yml --repo sds7788/zotero-arxiv-daily
gh api repos/sds7788/zotero-arxiv-daily/actions/workflows/main.yml --jq .state
# 应返回 active
gh workflow run main.yml --repo sds7788/zotero-arxiv-daily \
  --ref main -f dry_run=true
```

按步骤 2 的方式查看这次 main.yml 的新运行。当天没有新论文且 SEND_EMPTY=false 时，成功退出且不发信是正常情况；完整渲染的验证以步骤 2 为准。若任务再次报 runner 未获得，可以手动重新触发干跑；不要未经确认重跑可能已发送邮件的实际推送。

### 4. 验证恢复的定时推送

- 保留 `0 22 * * *`，即每日 UTC 22:00 / 北京时间次日 06:00，GitHub 可能延迟启动。
- 下一次定时任务应显示 `event=schedule` 且成功。存在新论文时，确认正常推荐邮件到达；同时检查垃圾箱。
- 如需立即发送一封真实测试邮件，必须另行获得确认，然后才手动运行 main.yml 并选择 `dry_run=false`。
- 真实发送后的验收才能证明 SMTP 凭据仍有效；本次离线测试和干跑都不能证明这一点。

## 防止再次停用

至少每 60 天内维护一次仓库，例如检查上游更新并合并需要的修复。持续无人维护而又要求长期定时运行时，应改用有持久调度的服务器。没有添加自动保活提交，也没有修改 Secrets 或创建额外通知任务。


## 授权后的执行结果（2026-10-08）

- 用户已明确确认合并修复、执行不发邮件的线上验证并恢复每日推送。
- PR #2 已合并，提交为 `3061a75a1d1b7ab26d0cc05d93bd8596f741ce5a`。合并后 GitHub 自动将每日工作流恢复为 `active`。
- [线上验证运行 37748208785](https://github.com/sds7788/zotero-arxiv-daily/actions/runs/37748208785) 已成功；job `113214709757` 的所有步骤成功，job 耗时 13 分 34 秒，总运行耗时约 13 分 38 秒。
- 完整依赖安装成功（1 分 17 秒），实际 Zotero 检索、过滤和排序成功；最近 5 篇论文全部完成本地模型生成和邮件渲染。
- 日志明确包含 `Dry run complete: recommendation email rendered; SMTP was not contacted.`；没有成功发信日志，未发送测试邮件。
- 代码链接服务返回非 JSON 响应时已成功降级，不妨碍本次推荐完成。
- 已在登录后的 Settings → Actions → General 核查：允许运行全部 Actions，日志保留期为 90 天；未修改仓库权限和 Secrets。
- 线上运行使用 Ubuntu 24.04。GitHub 给出 ubuntu-latest 将于 2026-10-19 开始迁移到 Ubuntu 26 的提示；两个工作流因此固定为 ubuntu-24.04，沿用已成功验证的操作系统。
- 在线上完整验证之后，另补充本地 LLM 输出最多 512 tokens 的保护（提交 `affdb37d10e50fcf0ede3c497d1e819d892b655e`）。锁定的 llama-cpp-python 0.3.2 官方接口支持该参数，输出预算离线检查及原 10 项回归测试通过；没有为这一附加限制重新运行完整模型。
- 保留每天 UTC 22:00 / 北京时间次日 06:00 的定时；下次预期触发是北京时间 2026-10-09 06:00，GitHub 可能延迟启动。当天无新论文且 SEND_EMPTY=false 时不发邮件。
- SMTP 凭据及收件箱投递未作实际发信验证，需以恢复后的正常定时邮件到达为准。原 Secrets 没有被查询或重设。
