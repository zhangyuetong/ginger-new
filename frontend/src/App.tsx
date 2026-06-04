import { useEffect, useState } from 'react'
import './App.css'

import { apiBase, fetchJson } from './api'

type EntryListRow = {
  id: number
  word: string
  colorIdx: number | null
  guessZh: string | null
  preview: string | null
  extras?: Record<string, unknown> | null
}

type Span = {
  kind: string
  value: string
  lemma?: string | null
  guessZh?: string | null
}

type Sense = {
  n: number | null
  text: string
  renderedSpans: Span[]
}

type PosBlock = {
  pos: string | null
  posGuessZh?: string | null
  senses: Sense[]
}

type RenderedDto = {
  posBlocks: PosBlock[]
}

type EntryDetail = {
  id: number
  word: string
  colorIdx: number | null
  definitionRaw: string | null
  definition: Record<string, unknown>
  extras: Record<string, unknown>
  rendered: RenderedDto
  guessZh: string | null
  updatedAt: string
}

type EntriesPage = {
  items: EntryListRow[]
  nextCursor: number | null
}

type SearchMode = 'lemma' | 'definition' | 'pos'
type WordMatch = 'prefix' | 'infix' | 'suffix'

function buildEntriesUrl(
  query: string,
  searchMode: SearchMode,
  wordMatch: WordMatch,
  cursor?: number | null,
): string {
  const params = new URLSearchParams({ limit: '120', query, searchMode })
  if (searchMode === 'lemma') {
    params.set('wordMatch', wordMatch)
  }
  if (cursor != null) {
    params.set('cursor', String(cursor))
  }
  return `/api/entries?${params.toString()}`
}

function searchPlaceholder(searchMode: SearchMode, wordMatch: WordMatch): string {
  if (searchMode === 'definition') return '释义中出现的整词…'
  if (searchMode === 'pos') return '词性，如 k. 或 sj.'
  if (wordMatch === 'infix') return '词条包含…'
  if (wordMatch === 'suffix') return '词条后缀…'
  return '词条前缀…'
}

async function patchGuess(id: number, guessZh: string): Promise<EntryDetail> {
  return fetchJson<EntryDetail>(`/api/entries/${id}/guess`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ guessZh }),
  })
}

function SenseText({
  text,
  spans,
  showRaw,
}: {
  text: string
  spans: Span[]
  showRaw: boolean
}) {
  if (showRaw) {
    return <div className="glossInline mono">{text}</div>
  }
  const safe = spans && spans.length > 0 ? spans : [{ kind: 'text', value: text }]
  return (
    <div className="glossInline mono">
      {safe.map((s, i) => {
        const key = `${i}:${s.kind}:${s.value}:${s.lemma ?? ''}`
        if (s.kind === 'gloss') {
          return (
            <span key={key} className="gloss hit" title={s.lemma ? `Lemma: ${s.lemma}` : undefined}>
              {s.value}
            </span>
          )
        }
        return (
          <span key={key} className="gloss">
            {s.value}
          </span>
        )
      })}
    </div>
  )
}

export default function App() {
  const [query, setQuery] = useState('')
  const [searchMode, setSearchMode] = useState<SearchMode>('lemma')
  const [wordMatch, setWordMatch] = useState<WordMatch>('prefix')
  const [items, setItems] = useState<EntryListRow[]>([])
  const [nextCursor, setNextCursor] = useState<number | null>(null)
  const [listLoading, setListLoading] = useState(false)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<EntryDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [guessDraft, setGuessDraft] = useState('')
  const [savingGuess, setSavingGuess] = useState(false)

  const [showRawSense, setShowRawSense] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const queryKey = query.trim()
  const listFetchKey = `${queryKey}|${searchMode}|${wordMatch}`

  useEffect(() => {
    let alive = true
    const ac = new AbortController()

    async function reloadList() {
      setListLoading(true)
      setErr(null)
      try {
        const page = await fetchJson<EntriesPage>(
          buildEntriesUrl(queryKey, searchMode, wordMatch),
          { signal: ac.signal },
        )
        if (!alive) return
        setItems(page.items)
        setNextCursor(page.nextCursor)
      } catch (e) {
        if (!alive) return
        if ((e as Error).name !== 'AbortError') {
          setErr((e as Error).message)
        }
      } finally {
        if (alive) setListLoading(false)
      }
    }

    void reloadList()
    return () => {
      alive = false
      ac.abort()
    }
  }, [listFetchKey])

  useEffect(() => {
    if (selectedId === null) return

    let alive = true
    const ac = new AbortController()
    async function reloadDetail(id: number) {
      setDetailLoading(true)
      setErr(null)
      try {
        const d = await fetchJson<EntryDetail>(`/api/entries/${id}`, { signal: ac.signal })
        if (!alive) return
        setDetail(d)
        setGuessDraft(d.guessZh ?? '')
      } catch (e) {
        if (!alive) return
        if ((e as Error).name !== 'AbortError') {
          setErr((e as Error).message)
        }
      } finally {
        if (alive) setDetailLoading(false)
      }
    }

    void reloadDetail(selectedId)
    return () => {
      alive = false
      ac.abort()
    }
  }, [selectedId])

  async function loadMore() {
    if (nextCursor === null || listLoading) return
    setListLoading(true)
    setErr(null)
    try {
      const page = await fetchJson<EntriesPage>(
        buildEntriesUrl(queryKey, searchMode, wordMatch, nextCursor),
      )
      setItems((xs) => xs.concat(page.items))
      setNextCursor(page.nextCursor)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setListLoading(false)
    }
  }

  async function saveGuess() {
    if (!detail) return
    setSavingGuess(true)
    setErr(null)
    setMsg(null)
    try {
      const updated = await patchGuess(detail.id, guessDraft)
      setDetail(updated)

      const guess = updated.guessZh
      setItems((xs) =>
        xs.map((r) =>
          r.id === updated.id
            ? { ...r, guessZh: guess, preview: guess ? r.preview : r.preview }
            : r,
        ),
      )

      setMsg('已保存推测')
      window.setTimeout(() => setMsg(null), 1500)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSavingGuess(false)
    }
  }

  const defs = detail?.definition as Record<string, unknown>
  const warns = defs?.parseWarnings
  const isErrorParse = defs?.error === true

  return (
    <div className="appShell">
      <aside className="listPane">
        <div className="toolbar">
          <div className="toolbarTitle">Ginger lexicon</div>
        </div>
        <div className="listScroller">
          <div className="toolbar searchToolbar">
            <div className="segmented" role="group" aria-label="搜索方式">
              <button
                type="button"
                className={searchMode === 'lemma' ? 'seg active' : 'seg'}
                onClick={() => setSearchMode('lemma')}
              >
                词条
              </button>
              <button
                type="button"
                className={searchMode === 'definition' ? 'seg active' : 'seg'}
                onClick={() => setSearchMode('definition')}
              >
                释义含词
              </button>
              <button
                type="button"
                className={searchMode === 'pos' ? 'seg active' : 'seg'}
                onClick={() => setSearchMode('pos')}
              >
                词性
              </button>
            </div>
            {searchMode === 'lemma' ? (
              <div className="segmented" role="group" aria-label="词条匹配">
                <button
                  type="button"
                  className={wordMatch === 'prefix' ? 'seg active' : 'seg'}
                  onClick={() => setWordMatch('prefix')}
                >
                  前缀
                </button>
                <button
                  type="button"
                  className={wordMatch === 'infix' ? 'seg active' : 'seg'}
                  onClick={() => setWordMatch('infix')}
                >
                  中缀
                </button>
                <button
                  type="button"
                  className={wordMatch === 'suffix' ? 'seg active' : 'seg'}
                  onClick={() => setWordMatch('suffix')}
                >
                  后缀
                </button>
              </div>
            ) : null}
            <div className="search">
              <label htmlFor="entry-search" className="sr-only">
                搜索
              </label>
              <input
                id="entry-search"
                placeholder={searchPlaceholder(searchMode, wordMatch)}
                value={query}
                title={searchPlaceholder(searchMode, wordMatch)}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="status">{listLoading ? '加载列表…' : ''}</div>
          </div>
          <div className="entryList">
            {items.map((row) => (
              <button
                key={row.id}
                type="button"
                className={`entryRow ${selectedId === row.id ? 'active' : ''}`}
                onClick={() => setSelectedId(row.id)}
              >
                <div className="wordLine">
                  <span className="word mono">{row.word}</span>
                  {row.guessZh ? (
                    <span className="lemmaGuess gloss hit mono">{row.guessZh}</span>
                  ) : null}
                </div>
                {row.preview ? (
                  <div className="preview mono">{row.preview}</div>
                ) : null}
              </button>
            ))}
          </div>
          <button type="button" className="loadMoreBtn" onClick={() => void loadMore()}>
            {nextCursor !== null ? '加载更多…' : '已到末尾'}
          </button>
        </div>
      </aside>

      <main className="detailPane">
        <div className="toolbar">
          <div className="toolbarTitle">词条详情</div>
          <button
            type="button"
            className="ghostBtn"
            onClick={() => setShowRawSense((x) => !x)}
          >
            {showRawSense ? '显示释义（含中文替换）' : '释义仅 Ginger 原文'}
          </button>
        </div>

        <div className="detailBody">
          {selectedId === null ? (
            <div className="status">请选择左侧一个词。</div>
          ) : detailLoading ? (
            <div className="status">加载详情…</div>
          ) : detail ? (
            <>
              {(msg || err) && (
                <div className="toolbar">
                  {msg ? <div className="status">{msg}</div> : null}
                  {err ? <div className="warn">{err}</div> : null}
                </div>
              )}
              {(isErrorParse || Array.isArray(warns)) && (
                <div className="warn">
                  {isErrorParse ? <div className="mono">解析结果为 error；请核对 definitionRaw。</div> : null}
                  {Array.isArray(warns) && warns.length > 0 ? (
                    <ul>
                      {(warns as unknown[]).map((w, i) => (
                        <li key={`w:${String(w)}:${String(i)}`} className="mono">
                          {String(w)}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}

              <div className="detailTitle">
                <div className="detailTitleMain">
                  <div className="headword mono">{detail.word}</div>
                  <div className="badgeRow">
                    {detail.colorIdx !== null ? <span className="chip mono">colorIdx {detail.colorIdx}</span> : null}
                    {detail.updatedAt ? <span className="chip mono">{detail.updatedAt}</span> : null}
                  </div>
                </div>

                <div className="guessBox">
                  <label className="muted" htmlFor="guessZh">
                    对该词的中文推测（SQLite 持久化）
                  </label>
                  <div className="guessActions">
                    <input
                      id="guessZh"
                      value={guessDraft}
                      onChange={(e) => setGuessDraft(e.target.value)}
                      placeholder='例如："（…）"，留空可清空'
                      autoComplete="off"
                      spellCheck={false}
                    />
                    <button
                      type="button"
                      className="primaryBtn"
                      disabled={savingGuess}
                      onClick={() => void saveGuess()}
                    >
                      {savingGuess ? '保存中…' : '保存推测'}
                    </button>
                  </div>
                  <div className="muted status">
                    后端接口：<span className="mono">{`${apiBase}/api/entries/${detail.id}/guess`}</span>
                  </div>
                </div>
              </div>

              {detail.definitionRaw ? (
                <div className="rawBox">
                  <div className="muted mono">definition_raw</div>
                  <div className="mono">{detail.definitionRaw}</div>
                </div>
              ) : null}

              {detail.rendered.posBlocks?.map((pb, pbIdx) => (
                <section key={`pb:${String(pb.pos ?? '')}:${pbIdx}`} className="pb">
                  <div className="pbTitle mono">
                    {pb.pos ? (
                      <>
                        <span>{`<${pb.pos}>`}</span>
                        {pb.posGuessZh ? (
                          <>
                            {' '}
                            <span className="gloss hit">{pb.posGuessZh}</span>
                          </>
                        ) : null}
                      </>
                    ) : (
                      `<unstructured>`
                    )}
                  </div>
                  {pb.senses.map((s, sIdx) => (
                    <div key={`sense:${pbIdx}:${sIdx}:${String(s.n ?? '')}:${s.text.slice(0, 24)}`} className="senseRow">
                      <div className="meta mono">
                        {typeof s.n === 'number' ? `义项序号：${String(s.n)}` : `义项`}
                      </div>
                      <SenseText text={s.text} spans={s.renderedSpans} showRaw={showRawSense} />
                    </div>
                  ))}
                </section>
              ))}

              {detail.extras && Object.keys(detail.extras).length > 0 ? (
                <details className="extras">
                  <summary>附加列 extras_json</summary>
                  <pre className="mono">{JSON.stringify(detail.extras, null, 2)}</pre>
                </details>
              ) : null}
            </>
          ) : (
            <div className="status">无法读取详情。</div>
          )}
        </div>
      </main>
    </div>
  )
}
