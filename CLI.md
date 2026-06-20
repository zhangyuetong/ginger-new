# Ginger 词典 CLI 脚手架

给 **Coding Agent** 用的命令行查词工具。一行命令即可在词典里查词，等价于人类在前端界面里的各种筛选操作。

- 脚本位置：[`backend/cli.py`](backend/cli.py)
- **直接读取** `backend/data/ginger.sqlite3`，**无需启动后端服务**（FastAPI/Vite 都不用跑）。
- 搜索与 gloss 中文替换的语义**与前端完全一致**：复用了 `backend/app/parser.py`、`render.py`。
- `set` 命令会写库，写入的是后端同一份数据，启动前端即可看到。

## 运行

```bash
cd backend
python cli.py <子命令> [参数]
```

> Windows 终端若中文乱码，脚本已强制 UTF-8 输出；仍异常可先 `set PYTHONUTF8=1`（bash 用 `export PYTHONUTF8=1`）。
> 用 `--db <路径>` 可指定其它 SQLite 文件（默认 `backend/data/ginger.sqlite3`）。

所有查询子命令都支持 `--json` 输出结构化结果，便于 agent 解析；不加则是人类友好的文本。

`word` / `def` / `pos` 都有 `--limit`（默认 80）。结果被截断时会提示**还有更多**：
文本模式末尾显示「显示前 N 条，还有更多；用 --limit 调大」，`--json` 模式返回
`{"items": [...], "count": N, "hasMore": true}`（做法是多取一条判断，不做全表计数）。

## 前端能力 ↔ CLI 子命令对照

| 前端界面操作 | CLI 子命令 |
| --- | --- |
| 词条搜索（前缀/中缀/后缀） | `word <q> [--match prefix\|infix\|suffix]` |
| 释义含词搜索（整词、词界匹配） | `def <word>` |
| 按词性搜索 | `pos <p>` |
| 点开词条看详情 / 义项 / 中文替换 | `show <id\|word>` |
| 「释义仅 Ginger 原文」开关 | `show <ref> --raw` |
| 左侧列表显示的已推测词义（gloss 词典） | `guesses` |
| 保存对某词的中文推测 | `set <id\|word> <中文>` |
| —（概览） | `stats` |

## 子命令详解

### `word` —— 按词条搜索
```bash
python cli.py word aa                 # 前缀 aa…
python cli.py word in --match suffix  # 后缀 …in
python cli.py word qr --match infix   # 包含 qr
python cli.py word aa --limit 200 --json
```
`--match` 默认 `prefix`，对应前端「前缀/中缀/后缀」三个按钮。

### `def` —— 释义中作为整词出现某词
```bash
python cli.py def taar      # 找释义里把 taar 当作完整单词用到的所有词条
```
与前端「释义含词」一致：**整词 + 词界**匹配（`taar` 不会命中 `taaru`）。用来反查「哪些词在用某个还没破译的词」。

### `pos` —— 含某词性块的词条
```bash
python cli.py pos k     # 或写 k.
python cli.py pos sj.
```
合法词性（13 个占位词）：`sj. k. e. i. a. hh. bu. p. q. cj. r. y.`。写 `k` 或 `k.` 均可，非法值会报错并列出全部可选项。

### `show` —— 词条详情
```bash
python cli.py show aa      # 按词形精确查
python cli.py show 1       # 按 id 查
python cli.py show aa --raw    # 只看 Ginger 原文，不替换
python cli.py show aa --json   # 含解析结构 definition + rendered
```
默认输出：词头、已有推测、`colorIdx`、原文、解析警告，以及**按义项渲染**的释义——**已猜中的词用《》括起替换的中文**，未猜的保持 Ginger 原文。`ref` 是纯数字按 id，否则按精确词形。

### `guesses` —— 全部已推测词（gloss 词典）
```bash
python cli.py guesses          # 每行：word<TAB>中文
python cli.py guesses --json
```
这就是渲染时用于中文替换的词典；开工前先看一遍已知词很有用。

### `set` —— 写入/清空推测
```bash
python cli.py set aohjg 房子    # 设置
python cli.py set aohjg ''      # 传空串清空
```
等价前端「保存推测」，**会写库**。写入后其它词条的渲染也会随之用上这个新 gloss。

### `stats` —— 概览
```bash
python cli.py stats
python cli.py stats --json
```
输出词条总数、已/未推测数量、合法词性列表、数据库路径。

## 给 Agent 的典型工作流

```bash
# 1. 看看进度和已知词
python cli.py stats
python cli.py guesses

# 2. 挑一个未破译词，看它的释义（用已知词辅助理解）
python cli.py show afsu

# 3. 反查：还有哪些词的释义用到了某个关键未知词，交叉印证
python cli.py def gudde

# 4. 按词性/词形找形态相关的词
python cli.py pos k.
python cli.py word afsu --match infix

# 5. 推断出含义后写回
python cli.py set afsu 移动
```
