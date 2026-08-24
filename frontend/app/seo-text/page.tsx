"use client";

import { useMemo, useState } from "react";
import { checkSeoText, fetchSeoTextPage, parseSeoTextTz, SeoTextAnalysis, SeoTextStyleAudit, SeoTextTz } from "@/lib/api";

const SAMPLE = `**ТЗ на текст**\n\n**URL:** https://site.ru/page/\n\n**Рекомендуемое количество слов:** 200 слов (1200 символов) - найдено 50 слов (300 символов)\n\n**Добавьте в текст ключевые слова**\n- ключевая фраза: 1 - 2 (найдено: 0)\n- слово: 2 - 4 (найдено: 0)\n\n**Добавьте в текст LSI**\n- тематическое слово\n\n**Настройки**\n**Главное ключевое слово:** ключевая фраза`;

export default function SeoTextPage() {
  const [tzText, setTzText] = useState("");
  const [text, setText] = useState("");
  const [parsed, setParsed] = useState<SeoTextTz | null>(null);
  const [analysis, setAnalysis] = useState<SeoTextAnalysis | null>(null);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");
  const [wordforms, setWordforms] = useState(true);
  const [loadedH1, setLoadedH1] = useState("");
  const [styleAudit, setStyleAudit] = useState<SeoTextStyleAudit | null>(null);

  const keywordProblems = useMemo(() => analysis?.keywords.filter(x => x.status !== "ok") ?? [], [analysis]);

  async function parseTz() {
    setLoading("Разбираю ТЗ…"); setError(""); setAnalysis(null);
    try { setParsed(await parseSeoTextTz(tzText)); }
    catch (e) { setError(e instanceof Error ? e.message : "Ошибка разбора ТЗ"); }
    finally { setLoading(""); }
  }

  async function loadUrl() {
    if (!parsed?.url) return;
    setLoading("Получаю текущий текст страницы…"); setError("");
    try { const result = await fetchSeoTextPage(parsed.url); setText(result.text); setLoadedH1(result.h1 || ""); }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось получить страницу"); }
    finally { setLoading(""); }
  }

  async function run() {
    setLoading("Проверяю SEO и естественность текста…"); setError("");
    try {
      const result = await checkSeoText({ tz_text: tzText, text, use_wordforms: wordforms });
      setParsed(result.tz);
      setAnalysis(result.analysis);
      setStyleAudit(result.style);
    }
    catch (e) { setError(e instanceof Error ? e.message : "Ошибка проверки"); }
    finally { setLoading(""); }
  }

  return <>
    <div className="topbar seoTextTopbar"><div><span className="eyebrow">Контент · SEO</span><h1>SEO-текст по ТЗ</h1><p>Разбирает ТЗ, считает независимые вхождения и проверяет готовый текст строго по правилам.</p></div></div>

    <section className="seoTextGrid">
      <div className="seoTextCard">
        <div className="sectionHead"><div><span className="eyebrow">Шаг 1</span><h2>Вставь ТЗ</h2></div><button className="button secondary" onClick={() => setTzText(SAMPLE)}>Пример</button></div>
        <textarea className="seoTextArea" rows={18} value={tzText} onChange={e=>setTzText(e.target.value)} placeholder="Вставь ТЗ целиком — URL, объём, ключи, LSI, настройки…" />
        <div className="seoTextActions"><button className="button primary" disabled={tzText.trim().length < 20 || !!loading} onClick={parseTz}>Разобрать ТЗ</button>{loading && <span>{loading}</span>}</div>
      </div>

      <div className="seoTextCard">
        <div className="sectionHead"><div><span className="eyebrow">Шаг 2</span><h2>Текст для проверки</h2></div>{parsed?.url && <button className="button secondary" disabled={!!loading} onClick={loadUrl}>Взять с URL</button>}</div>
        <textarea className="seoTextArea" rows={18} value={text} onChange={e=>setText(e.target.value)} placeholder="Вставь готовый/черновой текст или сначала разбери ТЗ и нажми «Взять с URL»." />
        <label className="seoTextCheck"><input type="checkbox" checked={wordforms} onChange={e=>setWordforms(e.target.checked)} /> Учитывать словоформы</label>
        <div className="seoTextRuleNote"><b>H1 считается по умолчанию.</b> При загрузке с URL ContentDesk автоматически добавляет H1 к основному тексту ровно один раз. При ручной вставке добавь H1 первой строкой вместе с текстом.</div>
        <div className="seoTextRuleNote"><b>Перед проверкой текст нормализуется:</b> полностью пустые строки и строки только из пробелов/табов удаляются. Непустые строки, слова, пунктуация и SEO-вхождения не изменяются. SEO- и редакторская проверка используют один и тот же нормализованный текст.</div>
        {loadedH1 && <div className="seoTextLoadedH1"><b>H1 с URL:</b> {loadedH1}</div>}
        <div className="seoTextActions"><button className="button dark" disabled={tzText.trim().length < 20 || text.trim().length < 1 || !!loading} onClick={run}>Проверить текст</button><span>{text ? `${text.split(/\r?\n/).filter(line => line.trim()).join("\n").trim().split(/\s+/).filter(Boolean).length} слов приблизительно` : ""}</span></div>
      </div>
    </section>

    {error && <div className="seoTextError">{error}</div>}

    {parsed && <section className="seoTextParsed">
      <div className="sectionHead"><div><span className="eyebrow">Распознано</span><h2>{parsed.main_keyword || "Требования к тексту"}</h2></div>{parsed.url ? <a className="textLink" href={parsed.url} target="_blank" rel="noreferrer">Открыть URL ↗</a> : <span className="textLink">URL не указан</span>}</div>
      <div className="seoTextKpis"><div><span>Рекомендуемый объём</span><strong>{parsed.recommended_words ?? "—"}</strong><small>слов по ТЗ</small></div><div><span>Ключей</span><strong>{parsed.keywords.length}</strong><small>с диапазонами</small></div><div><span>LSI</span><strong>{parsed.lsi.length}</strong><small>по 1 вхождению</small></div><div><span>Доп. запросов</span><strong>{parsed.additional_keywords.length}</strong><small>для ориентира</small></div></div>
      <div className="seoTextRuleNote"><b>Как считаем:</b> ключи независимы друг от друга. Если «бурильные трубы» засчитано как отдельный ключ, слово «трубы» внутри него не засчитывается как самостоятельное вхождение ключа «трубы». Между соседними ключевыми вхождениями должно быть минимум 2 других слова. Порядок слов внутри фразы сохраняется.</div>
    </section>}

    {styleAudit && <section className="seoTextCard seoHumanizerCard">
      <div className="sectionHead"><div><span className="eyebrow">Редакторская проверка</span><h2>Естественность текста</h2><p>{styleAudit.note}</p></div><div className={`seoHumanScore ${styleAudit.score >= 85 ? "good" : styleAudit.score >= 65 ? "warn" : "bad"}`}><strong>{styleAudit.score}</strong><span>/100</span></div></div>
      <div className="seoTextKpis result"><div><span>Замечаний</span><strong>{styleAudit.summary.total}</strong><small>стилистических</small></div><div><span>Высокий</span><strong>{styleAudit.summary.high}</strong><small>приоритет</small></div><div><span>Предложений</span><strong>{styleAudit.sentence_count}</strong><small>в тексте</small></div><div><span>Абзацев</span><strong>{styleAudit.paragraph_count}</strong><small>в тексте</small></div></div>
      {styleAudit.findings.length ? <div className="seoHumanFindings">{styleAudit.findings.map((f,i)=><article key={i} className={`seoHumanFinding ${f.severity}`}><div><b>{f.title}</b><span>{f.count > 1 ? ` · ${f.count}×` : ""}</span></div><p>{f.snippet}</p><small>{f.recommendation}</small></article>)}</div> : <div className="seoTextReady">✓ Явных стилистических проблем не найдено.</div>}
      {styleAudit.rewrite_first?.length > 0 && <div className="seoHumanBrief"><h3>Что переписать в первую очередь</h3><ol>{styleAudit.rewrite_first.map((f,i)=><li key={i}><b>{f.title}.</b> {f.recommendation}</li>)}</ol></div>}
      <div className="seoHumanBrief"><h3>Как переработать черновик</h3><ol>{styleAudit.brief.map((x,i)=><li key={i}>{x}</li>)}</ol></div>
      <details className="seoHumanProtected"><summary>Защищённые SEO-вхождения · {styleAudit.protected_keywords.length}</summary><p>Эти места уже используются для выполнения ТЗ. При перефразировании их лучше не менять без повторной SEO-проверки.</p>{styleAudit.protected_keywords.map((x,i)=><div key={i}><b>{x.phrase}</b><span> → {x.match_text}{!x.exact ? " · словоформа" : ""}</span><small>{x.snippet}</small></div>)}</details>
    </section>}

    {analysis && <>
      <section>
        <div className="sectionHead"><div><span className="eyebrow">Результат</span><h2>{analysis.summary.ready ? "Текст соответствует ТЗ" : "Есть что исправить"}</h2><p>{analysis.counting_note}</p></div></div>
        <div className="seoTextKpis result"><div><span>Слов</span><strong>{analysis.word_count}</strong><small>ориентир {analysis.recommended_words ?? "—"}</small></div><div><span>Ключи</span><strong>{analysis.summary.keywords_ok}/{analysis.summary.keywords_total}</strong><small>в норме</small></div><div><span>LSI</span><strong>{analysis.summary.lsi_found}/{analysis.summary.lsi_total}</strong><small>найдено</small></div><div><span>Расстояние</span><strong>{analysis.summary.spacing_violations}</strong><small>нарушений</small></div></div>
      </section>

      <section className="seoTextCard">
        <div className="sectionHead"><div><span className="eyebrow">Главная проверка</span><h2>Ключевые слова</h2><p>Зелёное — диапазон соблюдён; красное — не хватает; фиолетовое — перебор.</p></div></div>
        <div className="seoTextTableWrap"><table className="seoTextTable"><thead><tr><th>Ключ</th><th>Нужно</th><th>Найдено</th><th>Статус</th><th>Что сделать</th></tr></thead><tbody>{analysis.keywords.map(row=><tr key={row.phrase}><td><b>{row.phrase}</b>{row.matches?.slice(0,2).map((m,i)=><small key={i}>{m.match_text}{!m.exact ? " · словоформа" : ""}</small>)}</td><td>{row.min}–{row.max}</td><td>{row.count}</td><td><span className={`seoTextStatus ${row.status}`}>{row.status === "ok" ? "✓ Норма" : row.status === "missing" ? "Не хватает" : "Перебор"}</span></td><td>{row.status === "ok" ? "—" : row.status === "missing" ? `+${row.delta} самостоятельных вхожд.` : `−${row.delta} вхожд.`}</td></tr>)}</tbody></table></div>
      </section>

      <section className="seoTextTwoCols">
        <div className="seoTextCard"><span className="eyebrow">LSI</span><h2>Тематические слова</h2><div className="seoTextPills">{analysis.lsi.length ? analysis.lsi.map(x=><span key={x.phrase} className={x.found ? "ok" : "missing"}>{x.found ? "✓" : "+"} {x.phrase}</span>) : <span className="ok">LSI в ТЗ не задан</span>}</div></div>
        <div className="seoTextCard"><span className="eyebrow">Вывод</span><h2>План доработки</h2>{analysis.plan.length ? <ol className="seoTextPlan">{analysis.plan.map((x,i)=><li key={i}>{x}</li>)}</ol> : <p className="seoTextGood">По формальным требованиям ТЗ исправления не нужны.</p>}</div>
      </section>

      {analysis.spacing_violations.length > 0 && <section className="seoTextCard"><span className="eyebrow">Правило №2</span><h2>Слишком близкие вхождения</h2>{analysis.spacing_violations.map((x,i)=><div className="seoTextViolation" key={i}><b>«{x.first}» → «{x.second}»</b><span>между ними {x.gap_words} слов; нужно минимум 2</span><p>{x.snippet}</p></div>)}</section>}

      {keywordProblems.length === 0 && analysis.spacing_violations.length === 0 && <div className="seoTextReady">✓ Все обязательные ключевые вхождения находятся в заданных диапазонах и не нарушают правило расстояния.</div>}
    </>}
  </>;
}
