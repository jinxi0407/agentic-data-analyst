# QueryMate 发布验收

状态：**v1.2.0 候选，发布暂停，尚未合并 main、创建标签或推送。**
真实浏览器连接当前不可用，不能用 HTTP 200 或 Streamlit AppTest 代替实际页面验收。

## 现场与保护

- 工作分支：`agent-gate-timeout-diagnostic`。
- 起始 main 与 origin/main 均为 `4dc10f99c817bc14f3eee9d0c0b359540fb3cf72`，ahead/behind 为0/0。
- GitHub API 确认 `jinxi0407/agentic-data-analyst` 仍为 Private；未修改可见性。
- 起始本地与远端无 `v1.2.0`；旧分支与标签保持不变。
- 原索引问题先只读检查：无 index.lock、无索引文件持有者，索引可读。
  备份后一次普通 commit 成功，结果完整保存为 `0bb12e4`。
  未删除 index/lock，未 reset、改写历史或绕过锁；此前文件系统超时根因未能确定。
  后续普通 `git status --short` 的索引刷新再次报 `index.lock write error: Operation timed out`。
  只读检查 `GIT_OPTIONAL_LOCKS=0 git status --short` 成功，锁未残留、索引无进程持有。
  因写入问题复发，停止新的 Git 写操作，不无限重试；本轮 UI/文档/清理尚未提交。
- 备份前可用空间约1.7GiB，仅备份源码与证据，未清理其他项目或个人文件。

仓库外备份：

`/Users/jinxi/Documents/agentic-data-analyst-backups/querymate-pre-release-20260915-143123`

- 360个文件，源文件合计26,022,554字节，归档2,461,920字节。
- `worktree-with-uncommitted-evidence.tar.gz` SHA256：`4d43cba64d99f6d12ee92b578b3d895cf6f670650fd7aac33c8ac7295b16c2f4`。
- `manifest.json` SHA256：`245726cff3a86735990b3b0b6ad720937c6161c5de8bbce6b5d98a3ab68f91f2`。
- 每个归档成员已回读核对哈希。排除真实配置、虚拟环境、运行日志和 Git 目录；分支/标签及暂存状态另记于 manifest。

## 允许的改动

仅 UI 产品显示名、默认自动澄清、状态清理及对应测试，文档和已枚举文件清理。
API 缺省仍 direct。Gate、Prompt、JSON Schema、Pydantic、业务语义、SQL 引擎和评分不改。
原 freeze 的 UI 哈希保留；当前离线核验确认其余冻结文件无变化。

## 验收进度

- [x] 仓库外备份与逐文件校验。
- [x] 结果普通本地提交，未丢失评测证据。
- [x] 200题离线复核：OFF 138/200；ON 147/200；ON明确125/140。
- [x] 文件分类、引用检查及清理候选清单。
- [x] 执行清单内清理：42个已备份旧草稿归档，94个可再生缓存移除。
- [x] 完整 mock pytest：两次均为115 passed、2 warnings，最终运行30.67秒。
- [x] 少量固定真实 API 联调及失败记录：5次请求完成，含1次有效补充失败，未换题重试。
- [x] 启停、重复启动和 PID 归属验收：复用原 PID，停止成功，再启动成功。
- [ ] 实际浏览器交互验收，当前等待浏览器连接。
- [x] 工作树、当前暂存内容及5个待推送历史提交安全检查；原始命中和人工复核均保留。
- [ ] 验收通过后普通合并 main、附注标签 v1.2.0、仅推送 origin main 和该标签。

无真实浏览器验收时不宣称发布完成，不修改旧标签，不推送。

## 固定真实联调

协议与所有请求响应分别保存在 `eval/querymate_smoke_protocol.json`、`eval/querymate_smoke_results.json`。
这些是少量集成检查，不是新 Benchmark，也不修改200题成绩。

| 场景 | 状态 | 耗时 |
|---|---|---:|
| 明确问题 ON | success，原问题保留 | 3.894秒 |
| 指定城市但未说城市 ON | needs_clarification，未执行 SQL | 2.505秒 |
| 有效补充“南京市” | invalid_output，未执行 SQL | 5.626秒 |
| 无效补充“我暂时无法提供该信息” | needs_rephrase，未执行 SQL | 2.244秒 |
| 同一明确问题 OFF | success，无 clarification trace | 2.243秒 |

有效补充失败是当前冻结 Gate 的实际限制，不能声称本次真实完整双轮成功。
接口对外返回校验失败，内部具体原因未在本轮改动或推断。未更换问题、未重试覆盖失败，未修改核心。
普通 UI AppTest 验证了展示反问、补充提交、错误提示、新题状态清理和 OFF 接线；
实际浏览器未连接，因此不能据此声称页面人工/自动验收完成。

## 本地服务

重复启动复用 API PID 10958、UI PID 10961；停止脚本成功结束这两个归属核实的服务。
重新启动后 API PID 11321、UI PID 11346，均由本项目现有脚本登记。
MySQL 始终 healthy，端口 `127.0.0.1:3307 -> 3306`；没有重新 seed 或操作其他 Docker。
当前进程来自工作分支及未提交的 UI 接线，**不是已经发布的最终 main**。

## 安全与同步边界

安全审计见 `eval/querymate_security_audit.json`。扫描328个工作树文件和370个待推送历史中的
唯一文件版本；当前暂存区只有删除项，没有新增内容。模板占位值误命中与安全 URI 掩码均已复核，
没有发现真实密钥。后续提交内容或历史范围改变时，发布前仍需重新检查，不能沿用本次范围。
没有改动 `.env`、虚拟环境、数据库、业务配置或其他项目。

最终只读远端核对：main 仍为 `4dc10f99c817bc14f3eee9d0c0b359540fb3cf72`，
没有 `v1.2.0`，`v1.1.0` 附注对象仍为 `3b80e754367e33ba8b4665e9ea140e9e092fe16a`，
目标提交仍为 `2dc294fe43dc64658af7c85e7b60aae59a6be6a8`。
GitHub 仍为 Private；本轮只读访问，没有 push，也未向 upstream 写入。
本地 main 与远端 main 一致不代表本轮交付已同步：本轮成果仍在工作分支，UI/清理等改动未提交。

## 交接与待完成

1. Git 索引写入超时复发，保留现场，未尝试删除索引或绕过锁。
2. 浏览器后端未连接，真实页面待人工/自动确认。
3. 有效补充失败作为已知限制保留，不为发布改变冻结 Gate，不声称完整联调全绿。
4. 上述条件处理并验收通过后，才可普通提交、合并 main、创建附注标签并推送。

本轮未提交改动另存于仓库外候选快照：

`/Users/jinxi/Documents/agentic-data-analyst-backups/querymate-candidate-checkpoint-20260915-final-local`

其中 `manifest.json` 保存逐文件哈希、归档哈希、HEAD、分支、暂存状态与旧标签。
该快照与清理前备份同时保留；归档草稿从清理前备份或 `0bb12e4` 恢复。
快照不包含真实环境配置、虚拟环境、运行日志或 `.git`。
