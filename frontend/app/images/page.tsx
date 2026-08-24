"use client";

import { ChangeEvent, DragEvent, FormEvent, useMemo, useRef, useState } from "react";
import {
  ImageAuditResult,
  ImageProcessResult,
  ImageSiteAuditResult,
  auditImages,
  auditSiteImages,
  formatBytes,
  imageDownloadUrl,
  singleImageDownloadUrl,
  processImages,
} from "../../lib/api";

type Tab = "process" | "audit" | "site-audit";

const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];

export default function ImagesPage() {
  const [tab, setTab] = useState<Tab>("process");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [maxWidth, setMaxWidth] = useState(1920);
  const [outputFormat, setOutputFormat] = useState("webp");
  const [quality, setQuality] = useState(82);
  const [nameTemplate, setNameTemplate] = useState("image-{n}");
  const [processing, setProcessing] = useState(false);
  const [processError, setProcessError] = useState("");
  const [processResult, setProcessResult] = useState<ImageProcessResult | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const [auditUrl, setAuditUrl] = useState("");
  const [auditing, setAuditing] = useState(false);
  const [auditError, setAuditError] = useState("");
  const [auditResult, setAuditResult] = useState<ImageAuditResult | null>(null);

  const [siteAuditUrl, setSiteAuditUrl] = useState("");
  const [siteSitemapUrl, setSiteSitemapUrl] = useState("");
  const [siteLimit, setSiteLimit] = useState(30);
  const [siteAuditing, setSiteAuditing] = useState(false);
  const [siteAuditError, setSiteAuditError] = useState("");
  const [siteAuditResult, setSiteAuditResult] = useState<ImageSiteAuditResult | null>(null);

  const totalSelected = useMemo(() => files.reduce((sum, file) => sum + file.size, 0), [files]);

  function addFiles(incoming: File[]) {
    const valid = incoming.filter((file) => ACCEPTED.includes(file.type));
    setFiles((current) => {
      const map = new Map(current.map((file) => [`${file.name}-${file.size}-${file.lastModified}`, file]));
      valid.forEach((file) => map.set(`${file.name}-${file.size}-${file.lastModified}`, file));
      return Array.from(map.values()).slice(0, 60);
    });
    setProcessResult(null);
    setProcessError(incoming.length !== valid.length ? "Часть файлов пропущена: поддерживаются JPG, PNG и WebP." : "");
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    addFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  }

  function removeFile(index: number) {
    setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setProcessResult(null);
  }

  async function handleProcess(event: FormEvent) {
    event.preventDefault();
    if (!files.length) {
      setProcessError("Добавьте изображения для обработки.");
      return;
    }
    setProcessing(true);
    setProcessError("");
    setProcessResult(null);
    try {
      const result = await processImages(files, { maxWidth, outputFormat, quality, nameTemplate });
      setProcessResult(result);
    } catch (error) {
      setProcessError(error instanceof Error ? error.message : "Не удалось обработать изображения");
    } finally {
      setProcessing(false);
    }
  }

  async function handleAudit(event: FormEvent) {
    event.preventDefault();
    setAuditing(true);
    setAuditError("");
    setAuditResult(null);
    try {
      const result = await auditImages(auditUrl);
      setAuditResult(result);
    } catch (error) {
      setAuditError(error instanceof Error ? error.message : "Не удалось проверить изображения");
    } finally {
      setAuditing(false);
    }
  }

  async function handleSiteAudit(event: FormEvent) {
    event.preventDefault();
    setSiteAuditing(true);
    setSiteAuditError("");
    setSiteAuditResult(null);
    try {
      const result = await auditSiteImages({ url: siteAuditUrl, sitemap_url: siteSitemapUrl, limit: siteLimit });
      setSiteAuditResult(result);
    } catch (error) {
      setSiteAuditError(error instanceof Error ? error.message : "Не удалось проверить изображения сайта");
    } finally {
      setSiteAuditing(false);
    }
  }

  return (
    <>
      <header className="topbar auditTopbar">
        <div>
          <span className="eyebrow">ContentDesk · Images</span>
          <h1>Изображения</h1>
          <p>Подготовка файлов для сайта и технический контроль изображений на странице.</p>
        </div>
      </header>

      <div className="imageTabs">
        <button className={tab === "process" ? "imageTab active" : "imageTab"} onClick={() => setTab("process")}>Обработка файлов</button>
        <button className={tab === "audit" ? "imageTab active" : "imageTab"} onClick={() => setTab("audit")}>Аудит страницы</button>
        <button className={tab === "site-audit" ? "imageTab active" : "imageTab"} onClick={() => setTab("site-audit")}>Аудит сайта</button>
      </div>

      {tab === "process" ? (
        <>
          <div
            className={dragging ? "dropZone dragging" : "dropZone"}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInput.current?.click()}
          >
            <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={handleFileChange} />
            <div className="dropIcon">◇</div>
            <strong>Перетащите изображения сюда</strong>
            <p>или нажмите, чтобы выбрать файлы · JPG, PNG, WebP · до 60 файлов</p>
          </div>

          {files.length > 0 && (
            <section>
              <div className="sectionHead">
                <div><h2>Выбрано: {files.length}</h2><p>Общий исходный вес: {formatBytes(totalSelected)}</p></div>
                <button className="button" onClick={() => { setFiles([]); setProcessResult(null); }}>Очистить</button>
              </div>
              <div className="selectedFiles">
                {files.map((file, index) => (
                  <div className="selectedFile" key={`${file.name}-${file.lastModified}`}>
                    <div className="fileBadge">IMG</div>
                    <div className="grow"><strong>{file.name}</strong><span>{formatBytes(file.size)}</span></div>
                    <button className="fileRemove" onClick={() => removeFile(index)} aria-label="Удалить">×</button>
                  </div>
                ))}
              </div>
            </section>
          )}

          <form className="imageSettings" onSubmit={handleProcess}>
            <div className="sectionHead"><div><h2>Настройки обработки</h2><p>Размеры уменьшаются пропорционально, без растягивания изображения.</p></div></div>
            <div className="imageSettingsGrid">
              <label>Максимальная ширина
                <div className="inputSuffix"><input type="number" min={320} max={6000} value={maxWidth} onChange={(e) => setMaxWidth(Number(e.target.value))} /><span>px</span></div>
              </label>
              <label>Формат
                <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value)}><option value="webp">WebP</option><option value="jpeg">JPEG</option><option value="png">PNG</option></select>
              </label>
              <label>Качество
                <div className="rangeField"><input type="range" min={30} max={100} value={quality} onChange={(e) => setQuality(Number(e.target.value))} /><strong>{quality}%</strong></div>
              </label>
              <label>Шаблон имени
                <input value={nameTemplate} onChange={(e) => setNameTemplate(e.target.value)} placeholder="analiz-vozduha-{n}" />
                <small>Используйте <code>{"{n}"}</code> для номера и <code>{"{name}"}</code> для исходного имени.</small>
              </label>
            </div>
            {processError && <div className="auditError">{processError}</div>}
            <div className="imageActions"><button className="button primary" type="submit" disabled={processing || files.length === 0}>{processing ? "Обрабатываю…" : `Обработать ${files.length || ""} изображений`}</button></div>
          </form>

          {processing && <div className="auditLoading"><div className="loader"/><div><strong>Оптимизирую изображения</strong><p>ContentDesk меняет размер, формат и собирает готовые файлы.</p></div></div>}

          {processResult && (
            <section className="imageResult">
              <div className="resultHero">
                <div><span className="eyebrow">Готово</span><h2>{processResult.count} {processResult.count === 1 ? "изображение обработано" : "изображений обработано"}</h2><p>{processResult.count === 1 ? "Готовый файл можно скачать напрямую." : "Все готовые файлы собраны в ZIP-архив."}</p></div>
                {processResult.count === 1 ? (
                  <a className="button dark" href={singleImageDownloadUrl(processResult.job_id, processResult.files[0].output_name)}>Скачать изображение</a>
                ) : (
                  <a className="button dark" href={imageDownloadUrl(processResult.job_id)}>Скачать ZIP</a>
                )}
              </div>
              <div className="resultStats">
                <div><span>Было</span><strong>{formatBytes(processResult.total_before_bytes)}</strong></div>
                <div><span>Стало</span><strong>{formatBytes(processResult.total_after_bytes)}</strong></div>
                <div><span>Экономия</span><strong>{processResult.saved_percent}%</strong></div>
              </div>
              <div className="processedList">
                {processResult.files.map((file) => (
                  <div className="processedRow" key={file.output_name}>
                    <div className="grow"><strong>{file.source_name}</strong><span>→ {file.output_name}</span></div>
                    <div className="processedMeta"><span>{file.original_width}×{file.original_height} → {file.output_width}×{file.output_height}</span><strong>{formatBytes(file.before_bytes)} → {formatBytes(file.after_bytes)}</strong><em>−{file.saved_percent}%</em></div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      ) : tab === "audit" ? (
        <>
          <div className="auditInputPanel">
            <form className="auditForm" onSubmit={handleAudit}>
              <div className="auditInputWrap"><label>URL страницы</label><input value={auditUrl} onChange={(e) => setAuditUrl(e.target.value)} placeholder="https://example.ru/page/" required /></div>
              <button className="button primary auditButton" disabled={auditing}>{auditing ? "Проверяю…" : "Проверить изображения"}</button>
            </form>
            {auditError && <div className="auditError">{auditError}</div>}
          </div>

          {auditing && <div className="auditLoading"><div className="loader"/><div><strong>Проверяю изображения страницы</strong><p>Ищу ALT, дубли, большие файлы, битые URL, форматы и width/height.</p></div></div>}

          {auditResult && (
            <>
              <section>
                <div className="sectionHead"><div><h2>Результат аудита</h2><p>{auditResult.count} изображений · {auditResult.final_url}</p></div></div>
                <div className="imageAuditStats">
                  <div><span>Без ALT</span><strong>{auditResult.summary.missing_alt}</strong></div>
                  <div><span>Дубли ALT</span><strong>{auditResult.summary.duplicate_alt}</strong></div>
                  <div><span>&gt; 1 МБ</span><strong>{auditResult.summary.large_images}</strong></div>
                  <div><span>Битые</span><strong>{auditResult.summary.broken_images}</strong></div>
                  <div><span>Не WebP/AVIF</span><strong>{auditResult.summary.legacy_format}</strong></div>
                  <div><span>Без размеров</span><strong>{auditResult.summary.missing_dimensions}</strong></div>
                </div>
              </section>
              <section>
                <div className="sectionHead"><div><h2>Все изображения</h2><p>Проблемы показаны отдельно для каждого файла.</p></div></div>
                <div className="imageAuditTableWrap"><table className="imageAuditTable"><thead><tr><th>#</th><th>Изображение</th><th>ALT</th><th>Размер</th><th>HTTP</th><th>Проблемы</th></tr></thead><tbody>
                  {auditResult.images.map((image) => <tr key={`${image.index}-${image.src}`}><td>{image.index}</td><td className="imageUrlCell" title={image.src}>{image.src}</td><td>{image.alt || <span className="mutedText">—</span>}</td><td>{image.size_bytes ? formatBytes(image.size_bytes) : <span className="mutedText">—</span>}</td><td>{image.status_code ?? <span className="mutedText">—</span>}</td><td>{image.problems.length ? <div className="problemTags">{image.problems.map((problem) => <span key={problem}>{problem}</span>)}</div> : <span className="miniPill ok">OK</span>}</td></tr>)}
                </tbody></table></div>
              </section>
            </>
          )}
        </>
      ) : (
        <>
          <div className="auditInputPanel">
            <form className="auditForm" onSubmit={handleSiteAudit}>
              <div className="auditInputWrap"><label>URL сайта</label><input value={siteAuditUrl} onChange={(e) => setSiteAuditUrl(e.target.value)} placeholder="https://example.ru/" required /></div>
              <div className="auditInputWrap"><label>Sitemap</label><input value={siteSitemapUrl} onChange={(e) => setSiteSitemapUrl(e.target.value)} placeholder="https://example.ru/sitemap.xml — можно оставить пустым" /></div>
              <div className="auditInputWrap"><label>Лимит страниц</label><input type="number" min={1} max={100} value={siteLimit} onChange={(e) => setSiteLimit(Number(e.target.value))} /></div>
              <button className="button primary auditButton" disabled={siteAuditing}>{siteAuditing ? "Проверяю сайт…" : "Проверить изображения сайта"}</button>
            </form>
            {siteAuditError && <div className="auditError">{siteAuditError}</div>}
          </div>

          {siteAuditing && <div className="auditLoading"><div className="loader"/><div><strong>Проверяю изображения сайта</strong><p>Читаю sitemap, собираю изображения со страниц и проверяю ALT, вес, HTTP, формат и размеры.</p></div></div>}

          {siteAuditResult && <>
            <section>
              <div className="sectionHead"><div><h2>Аудит изображений сайта</h2><p>{siteAuditResult.pages_scanned} страниц · {siteAuditResult.unique_images} уникальных изображений · {siteAuditResult.image_occurrences} вхождений</p></div></div>
              <div className="imageAuditStats">
                <div><span>Без ALT</span><strong>{siteAuditResult.summary.missing_alt}</strong></div>
                <div><span>Дубли ALT</span><strong>{siteAuditResult.summary.duplicate_alt}</strong></div>
                <div><span>&gt; 1 МБ</span><strong>{siteAuditResult.summary.large_images}</strong></div>
                <div><span>Битые</span><strong>{siteAuditResult.summary.broken_images}</strong></div>
                <div><span>Не WebP/AVIF</span><strong>{siteAuditResult.summary.legacy_format}</strong></div>
                <div><span>Без размеров</span><strong>{siteAuditResult.summary.missing_dimensions}</strong></div>
              </div>
            </section>
            <section>
              <div className="sectionHead"><div><h2>Страницы</h2><p>Сначала удобно найти страницы с наибольшим количеством проблемных изображений.</p></div></div>
              <div className="imageAuditTableWrap"><table className="imageAuditTable"><thead><tr><th>URL</th><th>Изображений</th><th>С проблемами</th><th>Без ALT</th><th>HTTP</th></tr></thead><tbody>
                {[...siteAuditResult.pages].sort((a,b)=>b.problem_images-a.problem_images).map((page)=><tr key={page.url}><td className="imageUrlCell" title={page.url}>{page.url}</td><td>{page.images}</td><td>{page.problem_images}</td><td>{page.missing_alt}</td><td>{page.status_code ?? "—"}</td></tr>)}
              </tbody></table></div>
            </section>
            <section>
              <div className="sectionHead"><div><h2>Все найденные изображения</h2><p>Для каждого вхождения показана страница, ALT и технические проблемы.</p></div></div>
              <div className="imageAuditTableWrap"><table className="imageAuditTable"><thead><tr><th>Страница</th><th>Изображение</th><th>ALT</th><th>Размер</th><th>HTTP</th><th>Проблемы</th></tr></thead><tbody>
                {siteAuditResult.images.map((image,i)=><tr key={`${image.page_url}-${image.src}-${i}`}><td className="imageUrlCell" title={image.page_url}>{image.page_url}</td><td className="imageUrlCell" title={image.src}>{image.src}</td><td>{image.alt || <span className="mutedText">—</span>}</td><td>{image.size_bytes ? formatBytes(image.size_bytes) : <span className="mutedText">—</span>}</td><td>{image.status_code ?? <span className="mutedText">—</span>}</td><td>{image.problems.length ? <div className="problemTags">{image.problems.map((problem)=><span key={problem}>{problem}</span>)}</div> : <span className="miniPill ok">OK</span>}</td></tr>)}
              </tbody></table></div>
            </section>
          </>}
        </>
      )}
    </>
  );
}
