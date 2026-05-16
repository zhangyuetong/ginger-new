# Ginger 词典破译工作台

## 手写README

这是语言破译游戏Ginger的一个破译工作台。

整个程序均为AI所做，我无法保证其任何准确性。各位也可以继续扩展这个AI屎山，反正基本是一次性的。

运行方法：

后端：

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

以下为AI写的README，我没有看过，很可能过时。但如果AI要修改程序，建议也让他把README改了。

前后端分离：FastAPI + SQLite + React(Vite)。

## 目录

- [`backend/app`](backend/app)：后端 API、`definition` 解析、gloss 中文替换拼装
- [`frontend`](frontend)：React SPA  
- 词典表：仓库根目录 [`Ginger.xlsx`](Ginger.xlsx)，由后端在启动时读取并导入 SQLite

## SQLite 数据库

默认 SQLite 路径：`backend/data/ginger.sqlite3`（首次启动自动创建）。

## 后端启动

在 `backend` 目录：

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后会自动尝试读取 **仓库根下**（与 `backend` 同级）的 `Ginger.xlsx`，若存在即 **upsert** 导入数据库。  
若文件不在默认位置，可设环境变量 `GINGER_XLSX_PATH` 指向 `.xlsx` 绝对路径。  
若在开发时需要暂时跳过导入，可设 `SKIP_GINGER_XLS_IMPORT=1`。

控制台会打印导入摘要（created / updated / rows）。

首次启动还会在库里 **自动插入 13 个词性占位词条**（`sj.`、`k.`、`e.`、`i.`、`a.`、`hh.`、`bu.`、`p.`、`q.`、`cj.`、`r.`、`y.`），与普通词一样可以猜中文；义项块标题中会显示你已猜的中文。

释义解析 **仅此 13 个串 + 尾随空白** 才视为下一个词性块（形如 `sj. …`，不会把 `asj.` 误判成词性）。若改过解析逻辑，重启后端会再次 upsert `Ginger.xlsx` 并刷新已存词条的解析结果。

可选：跑一次解析器单元测试：

```bash
cd backend
python -m pytest tests/test_parser.py
```

Excel 必需列：**`word`**、**`definition`**；**`colorIdx`** 与其它列的规则与先前一致（见 `backend/app/ingest.py`）。

## 前端启动

默认 API：`http://127.0.0.1:8000`（[`frontend/.env.development`](frontend/.env.development) 中 `VITE_API_BASE`，可按需改）。

```bash
cd frontend
npm install
npm run dev
```

界面功能：前缀搜索、义项展示、gloss 中文替换、对每个词持久化推测等（**不包含**表格上传）。

## REST 概要

| 接口 | 说明 |
| --- | --- |
| `GET /api/health` | 存活检查 |
| `GET /api/entries?query=&cursor=&limit=` | 分页列表 |
| `GET /api/entries/{id}` | 详情 |
| `PATCH /api/entries/{id}/guess` | body：`{"guessZh": "..."}` ，空字符串会清空推测 |
