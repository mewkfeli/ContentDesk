"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { auditPage, AuditCheck, AuditResult, formatBytes } from "../../lib/api";

const CATEGORY_LABELS: Record<string, string> = {
  technical: "Техническое",
  metadata: "Метаданные",
  content: "Контент",
  links: "Ссылки",
  images: "Изображения",
};

function StatusIcon({ status }: { status: AuditCheck["status"] }) {
  return <span className={`auditStatus ${status}`}>{status === "good" ? "✓" : status === "warning" ? "!" : "×"}</span>;
}

export default function Page() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<AuditResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const value = new URLSearchParams(window.location.search).get("url");
    if (value) setUrl(value);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      setResult(await auditPage(url));
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Не удалось выполнить аудит");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <header className="topbar auditTopbar">
        <div>
          <span className="eyebrow">ContentDesk</span>
          <h1>SEO-аудит страницы</h1>
          <p>Проверяем HTML, метаданные, структуру контента, ссылки и изображения.</p>
        </div>
        <div className="headerActions"><Link href="/audit/descriptions" className="button">Аудит Description</Link><Link href="/audit/indexing" className="button dark">Проверка индексации →</Link></div>
      </header>

      <section className="auditInputPanel">
        <form className="auditForm" onSubmit={submit}>
          <div className="auditInputWrap">
            <label htmlFor="audit-url">URL страницы</label>
            <input
              id="audit-url"
              type="text"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://example.ru/service/"
              autoComplete="url"
            />
          </div>
          <button className="button primary auditButton" disabled={loading || !url.trim()}>
            {loading ? "Проверяю…" : "Проверить страницу"}
          </button>
        </form>
        {error && <div className="auditError">{error}</div>}
      </section>

      {loading && (
        <div className="auditLoading">
          <span className="loader" />
          <div><strong>Анализируем страницу</strong><p>Получаем HTML и собираем основные SEO-показатели.</p></div>
        </div>
      )}

      {result && !loading && (
        <div className="auditResults">
          <section className="scorePanel">
            <div className="scoreHero">
              <div className={`scoreCircle ${result.score >= 85 ? "great" : result.score >= 65 ? "medium" : "low"}`}>
                <strong>{result.score}</strong><span>/ 100</span>
              </div>
              <div>
                <span className="eyebrow">Результат аудита</span>
                <h2>{result.summary.title || "Страница без Title"}</h2>
                <a href={result.final_url} target="_blank" rel="noreferrer">{result.final_url}</a>
                <p>{result.issues_count === 0 ? "Критичных замечаний не найдено." : `Найдено замечаний: ${result.issues_count}`}</p>
              </div>
            </div>
            <div className="breakdownGrid">
              {Object.entries(result.breakdown).map(([key, value]) => (
                <div className="breakdownItem" key={key}>
                  <div><span>{CATEGORY_LABELS[key]}</span><strong>{value}</strong></div>
                  <div className="progress"><i style={{ width: `${value}%` }} /></div>
                </div>
              ))}
            </div>
          </section>

          <section>
            <div className="sectionHead"><div><h2>Проверки</h2><p>Что уже хорошо и что стоит поправить на странице.</p></div></div>
            <div className="checksPanel">
              {result.checks.map((check, index) => (
                <div className="checkRow" key={`${check.category}-${check.label}-${index}`}>
                  <StatusIcon status={check.status} />
                  <div className="checkMain">
                    <div className="checkTitle"><strong>{check.label}</strong><span>{CATEGORY_LABELS[check.category]}</span></div>
                    <p>{check.value}</p>
                    {check.recommendation && check.status !== "good" && <div className="recommendation">{check.recommendation}</div>}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section>
            <div className="sectionHead"><div><h2>Краткая сводка</h2><p>Основные данные, которые ContentDesk извлёк со страницы.</p></div></div>
            <div className="statGrid">
              <div className="statCard"><span>Слов</span><strong>{result.summary.word_count}</strong></div>
              <div className="statCard"><span>H2 / H3</span><strong>{result.summary.h2_count} / {result.summary.h3_count}</strong></div>
              <div className="statCard"><span>Внутренних ссылок</span><strong>{result.summary.internal_links}</strong></div>
              <div className="statCard"><span>Изображений</span><strong>{result.summary.images}</strong></div>
              <div className="statCard"><span>Без ALT</span><strong>{result.summary.missing_alt}</strong></div>
              <div className="statCard"><span>Тяжёлых &gt;1 МБ</span><strong>{result.summary.large_images}</strong></div>
            </div>
          </section>

          {result.images.length > 0 && (
            <section>
              <div className="sectionHead"><div><h2>Изображения страницы</h2><p>ALT и размер, если сервер изображения сообщает Content-Length.</p></div></div>
              <div className="imageAuditTableWrap">
                <table className="imageAuditTable">
                  <thead><tr><th>#</th><th>Изображение</th><th>ALT</th><th>Размер</th><th>Статус</th></tr></thead>
                  <tbody>
                    {result.images.map((image) => {
                      const badAlt = !image.alt;
                      const heavy = (image.size_bytes ?? 0) > 1_000_000;
                      return (
                        <tr key={`${image.index}-${image.src}`}>
                          <td>{image.index}</td>
                          <td className="imageUrlCell" title={image.src}>{image.src || "—"}</td>
                          <td>{image.alt || <span className="mutedText">Не задан</span>}</td>
                          <td>{image.size_bytes ? formatBytes(image.size_bytes) : "—"}</td>
                          <td><span className={`miniPill ${badAlt ? "bad" : heavy ? "warn" : "ok"}`}>{badAlt ? "Нет ALT" : heavy ? "Тяжёлое" : "OK"}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      )}
    </>
  );
}
