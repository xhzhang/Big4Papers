# SecAtlas 静态发布

`static-publish` 是只读发布分支，面向 Vercel 免费版。它不包含在线更新接口；论文搜索、会议/年份/Track/Topic/标签筛选、论文对比、研读列表、列表分组与 Excel 导出均在浏览器本地运行。

## 数据边界

- `data/papers.sqlite3` 是本地权威数据库，由 Git 忽略，不上传到 Vercel。
- `public/catalog.json` 是从 SQLite 导出的完整网页快照，包含 4,436 篇论文当前可发布的全部处理字段。
- 构建时 Next.js 会把网页和 `catalog.json` 一起导出到 `out/`。
- 研读列表和常用方向保存在浏览器 `localStorage`，不需要云数据库。

## 本地验证

```powershell
pnpm install --frozen-lockfile
pnpm test
pnpm start
```

打开 `http://localhost:3000/`。`pnpm start` 只预览已经生成的 `out/`，不会启动数据更新服务。

## Vercel 设置

将仓库导入 Vercel，并把 Production Branch 设为 `static-publish`。仓库中的 `vercel.json` 已固定：

- 安装命令：`pnpm install --frozen-lockfile`
- 构建命令：`pnpm build`
- 输出目录：`out`
- Framework Preset：Other

不需要环境变量、数据库或 Serverless Function。

## 以后更新数据

1. 在开发分支本地更新 SQLite，并重新导出 `public/catalog.json`。
2. 将新的 `public/catalog.json` 同步到 `static-publish`。
3. 在 `static-publish` 运行 `pnpm test`。
4. 提交并推送；Vercel 会发布新的静态快照。

发布分支不会直接修改 SQLite，也不会在网页上提供“更新数据”按钮。
