# GitHub Pages 发布

`gh` 是 SecAtlas 的 GitHub Pages 专用分支。它发布纯静态快照，不需要服务器、云数据库或运行时 API。

## 首次启用

1. 将 `gh` 分支推送到 GitHub。
2. 打开仓库 **Settings → Pages**。
3. 在 **Build and deployment** 中把 Source 设为 **GitHub Actions**。
4. 打开 **Actions**，等待 **Deploy SecAtlas to GitHub Pages** 完成；以后每次推送 `gh` 都会自动重新发布，也可以手动运行工作流。

工作流会自动识别两类地址：

- 用户或组织站点：`https://<owner>.github.io/`
- 项目站点：`https://<owner>.github.io/<repository>/`

因此无需手工修改仓库名或资源路径。

## 本地验证

```powershell
pnpm install --frozen-lockfile
$env:SECATLAS_BASE_PATH = "/Big4Papers/"
pnpm test
python -m http.server 3000 --directory dist/client
```

构建产物位于 `dist/client/`，其中包含 `.nojekyll` 和 `404.html`。本地以根路径预览时可不设置 `SECATLAS_BASE_PATH`。

## 更新论文数据

GitHub Pages 上不会显示“更新数据”按钮。未来在本地更新 SQLite 后，重新导出并提交以下静态文件，再把改动合并进 `gh`：

- `public/catalog.json`
- `public/catalog-papers/{year}.json`
- `public/catalog-details/{year}.json`

推送后工作流会自动发布新的论文快照。
