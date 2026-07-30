# SecAtlas 静态发布

`static-publish` 是面向 Vercel 的只读发布分支。搜索、筛选、Track 映射追溯、论文对比、团队脉络、研读列表、分组和 Excel 导出均在浏览器中运行；网页不会连接 SQLite，也不会显示“更新数据”按钮。

## 数据边界

- `data/papers.sqlite3` 是本地权威数据库，由 Git 忽略，不上传到 Vercel。
- `public/catalog.json` 保存轻量元数据与分片清单。
- `public/catalog-papers/{year}.json` 保存年度论文索引，`public/catalog-details/{year}.json` 保存按需加载的英文摘要。
- 当前静态快照覆盖 2023—2026 年四个会议，共 4,436 篇论文。
- 研读列表、分组和常用方向保存在浏览器 `localStorage` 中，不需要云数据库。

## 本地验证

```powershell
pnpm install --frozen-lockfile
pnpm test
python -m http.server 3000 --directory dist/client
```

打开 `http://localhost:3000/`。静态构建产物位于 `dist/client/`。

## Vercel 设置

将仓库导入 Vercel，并把 Production Branch 设为 `static-publish`。仓库中的 `vercel.json` 已固定：

- 安装命令：`pnpm install --frozen-lockfile`
- 构建命令：`pnpm build`
- 输出目录：`dist/client`
- Framework Preset：Other

不需要环境变量、云数据库或 Serverless Function。

## 后续更新数据

1. 在开发分支本地更新 SQLite，并重新导出 `public/catalog.json` 及两个年度分片目录。
2. 将最新功能与数据合并到 `static-publish`。
3. 在 `static-publish` 运行 `pnpm test`。
4. 提交并推送，Vercel 会发布新的静态快照。

发布分支不会直接修改 SQLite；数据更新仍在本地完成。
