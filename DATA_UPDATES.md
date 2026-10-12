# 数据更新记录

## 2026-10-12

本轮核对会议官网、正式主会日程及必要的作者原文来源。论文库覆盖 2023—2026 年，共 4,909 篇；2026 年的研究论文口径如下：

| 会议 | 收录数 | 本轮处理 |
| --- | ---: | --- |
| IEEE S&P | 254 | 补入两篇此前漏收论文；保留一篇 2025 年录用、延迟至 2026 年展示的事实；补齐 Session 和 254 个 DOI |
| ACM CCS | 483 | 正式录用页 482 篇，加官方日程与作者页面共同证实的 GPUThor；补齐官方 Session |
| USENIX Security | 362 | 排除 18 条 Enigma 邀请报告，不计历史论文 Test of Time 讨论；补齐全部研究论文 PDF |
| NDSS | 265 | 本轮核对后论文数量保持不变 |

CCS 原数据中的 196 条错年条目来自官网 HTML 注释里的历史模板，已归档，不代表论文撤稿。另归档 USENIX 的 18 条邀请报告；归档记录及更新前的 SQLite 备份保留在本地，不上传公开仓库。

### 摘要、概述和分类

- S&P 新补充 83 篇可靠英文原文摘要及 66 个开放 PDF；8 个出版改题记录通过唯一作者集合人工核对，仅补 DOI，不据此导入近似标题的摘要。
- GPUThor 摘要来自 arXiv 2609.16546，PDF 指向作者开放论文；保留“官方日程有、录用列表暂缺”的来源区别。
- 清理或替换全库 11 条仓库/工件说明、禁运提示或索引状态文字，不能将这些内容当作论文摘要；其中两篇旧 USENIX 论文补回官网现已公开的原文摘要。
- 本轮重新生成 465 篇中文概述。没有英文摘要的条目仅作保守标题说明，并明确标注“仅从标题可知”；不补写不存在的方法、实验和结论。
- CCS 2026 的 53 个官方 Session 主题都映射至现有跨会、跨年 Track；分类规则版本为 `2026.10-v1`，没有新增重复年度 Track。

### 官方核对入口

- [S&P 录用列表](https://sp2026.ieee-security.org/accepted-papers.html)、[会议日程](https://sp2026.ieee-security.org/program.html)
- [CCS 录用列表](https://www.sigsac.org/ccs/CCS2026/program/accepted-papers.html)、[主会日程](https://www.sigsac.org/ccs/CCS2026/program/schedule.html)
- [USENIX 技术论文与日程](https://www.usenix.org/conference/usenixsecurity26/technical-sessions)
- [NDSS 录用列表](https://www.ndss-symposium.org/ndss2026/accepted-papers/)
- [GPUThor 作者项目](https://gputhor.com/)、[arXiv 原文](https://arxiv.org/abs/2609.16546)

CCS 2026 会议尚未举行，后续正式论文集发布后仍需复核；当前收录数不等于最终出版量。覆盖状态中的数字是本次核对快照，不是自动声明永久完整。
