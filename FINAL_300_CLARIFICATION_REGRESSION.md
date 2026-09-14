# Fixed 300-case Clarification Regression

## 首轮配对结果

```text
Fixed 300-case Regression Benchmark

Clarification OFF
Accuracy = 77.33% (232/300)
Avg latency = 2.76s

Clarification ON
First-turn Result Accuracy = 33.00% (99/300)
Avg latency = 7.96s
Clarification Trigger Rate = 122/300 (40.67%)

Delta = -44.33 pp
```

| 指标 | OFF | ON |
|---|---:|---:|
| P50 latency (s) | 2.196696 | 7.226212 |
| P95 latency (s) | 6.876529 | 13.076583 |
| Average model calls | 1.08 | 1.82 |
| Model calls observed | 324 | 546 |
| Missing call-count cases | 0 | 0 |
| Missing token-usage calls | 0 | 0 |
| 首轮完成率 | 298/300（99.33%） | 138/300（46.00%） |

首轮完成定义：无需用户补充且 SQL 执行成功；不等同于结果正确。
准确率始终基于 SQL 结果与原 Ground Truth 的严格比较，分母均为300。
耗时为工作线程中生产调用的墙钟时间，含Gate和原有重试，不含排队、结果落盘或用户思考。
P50为中位数，P95为nearest-rank。模型调用由原capture_usage统计；SDK内部网络重试不是单独模型调用。

## Gate与逐题配对

Proceed = 138；Clarify = 122。
Proceed子集结果准确率：99/138（71.74%）。这是条件子集指标，不能替代99/300的全集成绩。
其他状态与计数：`{"proceed": 138, "clarify": 122, "invalid_output": 37, "needs_rephrase": 3}`。

| 配对 | 题数 |
|---|---:|
| OFF正确 → ON正确 | 99 |
| OFF正确 → ON错误/未完成 | 133 |
| OFF错误 → ON正确 | 0 |
| OFF错误 → ON错误/未完成 | 68 |

配对回退中ON状态分布：`{"needs_clarification": 91, "invalid_output": 37, "success": 3, "needs_rephrase": 2}`。
也就是原本OFF答对的133题中，130题在开启Gate后未完成首轮查询：91题反问、37题结构或证据校验失败、2题要求重述。
其余3题执行成功但结果不匹配。这些状态不被合并称为“SQL执行错误”，也不把91个反问直接定性为“不必要澄清”。
这是本次开启设置后的观测回退；两次独立SQL采样仍有随机性，不能把全部差异都归因为反问。

在这套固定任务的无补充回答条件下，开启Gate明显降低了首轮结果准确率和完成率，并增加耗时。
这个结论只涉及本次首轮回归，不否认另一套120题中获得额外用户信息后的交互收益。
本次不据此修改Gate、Prompt、参数或问题，生产端现有默认关闭设置也没有变更。

### 触发澄清的case id

final_release_300_002, final_release_300_003, final_release_300_004, final_release_300_005, final_release_300_007, final_release_300_008, final_release_300_009, final_release_300_010, final_release_300_018, final_release_300_021, final_release_300_024, final_release_300_029, final_release_300_032, final_release_300_034, final_release_300_039, final_release_300_044, final_release_300_045, final_release_300_049, final_release_300_050, final_release_300_057, final_release_300_058, final_release_300_059, final_release_300_060, final_release_300_064, final_release_300_066, final_release_300_067, final_release_300_068, final_release_300_069, final_release_300_073, final_release_300_077, final_release_300_078, final_release_300_080, final_release_300_083, final_release_300_085, final_release_300_086, final_release_300_087, final_release_300_092, final_release_300_093, final_release_300_097, final_release_300_100, final_release_300_104, final_release_300_106, final_release_300_113, final_release_300_115, final_release_300_118, final_release_300_120, final_release_300_121, final_release_300_123, final_release_300_124, final_release_300_127, final_release_300_131, final_release_300_134, final_release_300_135, final_release_300_137, final_release_300_138, final_release_300_139, final_release_300_141, final_release_300_144, final_release_300_147, final_release_300_156, final_release_300_159, final_release_300_160, final_release_300_161, final_release_300_162, final_release_300_163, final_release_300_170, final_release_300_172, final_release_300_175, final_release_300_176, final_release_300_177, final_release_300_181, final_release_300_183, final_release_300_184, final_release_300_186, final_release_300_189, final_release_300_191, final_release_300_194, final_release_300_197, final_release_300_198, final_release_300_199, final_release_300_200, final_release_300_202, final_release_300_205, final_release_300_206, final_release_300_208, final_release_300_210, final_release_300_215, final_release_300_222, final_release_300_224, final_release_300_226, final_release_300_227, final_release_300_229, final_release_300_230, final_release_300_231, final_release_300_232, final_release_300_234, final_release_300_235, final_release_300_242, final_release_300_245, final_release_300_247, final_release_300_249, final_release_300_253, final_release_300_256, final_release_300_258, final_release_300_259, final_release_300_262, final_release_300_263, final_release_300_267, final_release_300_270, final_release_300_271, final_release_300_273, final_release_300_274, final_release_300_275, final_release_300_280, final_release_300_281, final_release_300_282, final_release_300_283, final_release_300_284, final_release_300_285, final_release_300_288, final_release_300_290, final_release_300_294

### OFF正确而ON错误/未完成的case id

final_release_300_002, final_release_300_003, final_release_300_004, final_release_300_005, final_release_300_008, final_release_300_010, final_release_300_013, final_release_300_014, final_release_300_018, final_release_300_020, final_release_300_027, final_release_300_029, final_release_300_034, final_release_300_036, final_release_300_039, final_release_300_044, final_release_300_045, final_release_300_049, final_release_300_050, final_release_300_051, final_release_300_056, final_release_300_057, final_release_300_059, final_release_300_060, final_release_300_061, final_release_300_063, final_release_300_064, final_release_300_067, final_release_300_068, final_release_300_069, final_release_300_072, final_release_300_073, final_release_300_075, final_release_300_078, final_release_300_079, final_release_300_080, final_release_300_083, final_release_300_085, final_release_300_087, final_release_300_090, final_release_300_092, final_release_300_093, final_release_300_097, final_release_300_103, final_release_300_104, final_release_300_105, final_release_300_106, final_release_300_113, final_release_300_117, final_release_300_118, final_release_300_121, final_release_300_124, final_release_300_126, final_release_300_127, final_release_300_133, final_release_300_134, final_release_300_135, final_release_300_137, final_release_300_139, final_release_300_144, final_release_300_147, final_release_300_154, final_release_300_156, final_release_300_158, final_release_300_159, final_release_300_160, final_release_300_161, final_release_300_162, final_release_300_163, final_release_300_167, final_release_300_172, final_release_300_173, final_release_300_178, final_release_300_180, final_release_300_182, final_release_300_183, final_release_300_185, final_release_300_187, final_release_300_189, final_release_300_191, final_release_300_194, final_release_300_197, final_release_300_199, final_release_300_200, final_release_300_202, final_release_300_206, final_release_300_209, final_release_300_210, final_release_300_217, final_release_300_218, final_release_300_222, final_release_300_224, final_release_300_227, final_release_300_229, final_release_300_230, final_release_300_232, final_release_300_234, final_release_300_235, final_release_300_237, final_release_300_242, final_release_300_245, final_release_300_247, final_release_300_248, final_release_300_249, final_release_300_250, final_release_300_253, final_release_300_256, final_release_300_258, final_release_300_259, final_release_300_260, final_release_300_262, final_release_300_263, final_release_300_267, final_release_300_268, final_release_300_269, final_release_300_270, final_release_300_271, final_release_300_272, final_release_300_273, final_release_300_274, final_release_300_275, final_release_300_277, final_release_300_279, final_release_300_280, final_release_300_281, final_release_300_284, final_release_300_285, final_release_300_288, final_release_300_290, final_release_300_292, final_release_300_294, final_release_300_295, final_release_300_297

## 协议与证据

生产代码固定为 `2dc294fe43dc64658af7c85e7b60aae59a6be6a8`（`v1.1.0`），没有修改生产逻辑、Prompt、Gate、城市元数据或评分代码。
使用原 `eval/final_release_holdout_300.json` 和 `eval/final_release_manifest.json`；
参考日期2026-09-12，原seed与七张表指纹不变；没有重新seed、改城市、修改Ground Truth或删除失败题。
两边使用qwen-plus，同一个SQL temperature；Gate保持原temperature=0。具体参数与SDK超时默认值见freeze。
每种模式最多4并发，按20题批次交替先后顺序；共享只读城市缓存预热，不调用embedding。
每题每种模式首次运行一次，保留生产重试但不增加评测重试；已保存调用不重复执行。
候选入口只接受原问题、参考日期、开关；没有传入标准SQL、Ground Truth或评测标签。
ON触发反问后立即结束，没有任何模拟用户回答；needs_rephrase、invalid_output和system_error等同样保留在总分母。
原题库与manifest没有should_clarify标签，也未提供可核验的全体必须proceed协议，因此只报告Trigger Rate，不把所有反问定性为不必要澄清。
同时只读审阅了历史生成脚本 `4000bba0048a6ea571d3b26262c6c58454173b80:eval/final_release_holdout_300.py`，未发现全体必须直接回答的澄清判定约定；没有执行或修改该生成器。
配对逐题结果及全部失败案例分别见 `eval/clarification_300_regression_per_case.json` 与 `_bad_cases.json`。
完整首次调用、usage、反问及错误见 `eval/clarification_300_regression_events.jsonl`；冻结配置与文件哈希见 `_freeze.json`。
若发生启动后中断且模型完成状态不可确认，保留为未完成、不重跑，并单独报告缺失耗时/调用统计。
本次实际中断为0；两边各300题均有完整耗时与调用记录，捕获的870次高层模型调用均返回ok，未记录API/传输失败；不推断SDK内部是否曾有已恢复的网络重试。
审计确认OFF的Gate决策数为0、用户补充回答为0、使用的补充槽位为0；138组可对照SQL输入及其alias normalization结果完全一致。
完整性记录见 `eval/clarification_300_regression_integrity.json`。所有原生产文件、既有评测文件及数据库指纹均保持冻结版本。

## 与120题评测的边界

本报告是已揭晓的300题回归测试，只测开启Gate对首轮原查询能力的影响，不是新盲测。
120题专项评测衡量允许一轮用户补充的交互收益：59.17% → 73.33%，+14.17pp，Clarification F1 93.10%。
两者题库、可用信息和目的不同，不拼接准确率、延迟或提升百分点；F1不是端到端准确率。
没有根据本次成绩调整系统或题目。

## 测试

评测完成后再次运行pytest：**74 passed, 1 warning in 16.58s**；runner离线自检通过。
warning为Starlette TestClient使用AnyIO旧别名的弃用提示。
完整输出见 `eval/clarification_300_regression_pytest.json`。
