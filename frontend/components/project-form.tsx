"use client";

import { FormEvent, useState } from "react";
import { createProject } from "@/lib/api";
import { showToast } from "@/components/toast-provider";

export function ProjectForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");

    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await createProject({
        name: String(form.get("name") ?? ""), domain: String(form.get("domain") ?? ""),
        cms: String(form.get("cms") ?? ""), project_type: String(form.get("project_type") ?? ""),
        content_style: String(form.get("content_style") ?? ""),
      });
      formElement.reset();
      setOpen(false);
      onCreated();
      showToast("Проект добавлен");
    } catch (err) { const message = err instanceof Error ? err.message : "Ошибка"; setError(message); showToast(message, "error"); }
    finally { setBusy(false); }
  }

  return <>
    <button className="button primary" onClick={() => setOpen(true)}>＋ Добавить проект</button>
    {open && <div className="modalBackdrop" onMouseDown={() => setOpen(false)}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modalHead"><div><span className="eyebrow">Новый проект</span><h2>Добавить сайт</h2></div><button className="iconButton" onClick={() => setOpen(false)}>×</button></div>
        <form onSubmit={submit} className="formGrid">
          <label>Название<input name="name" required placeholder="ЭкоЛаб" /></label>
          <label>Домен<input name="domain" required type="url" placeholder="https://example.ru" /></label>
          <label>CMS<input name="cms" placeholder="WordPress" /></label>
          <label>Тип проекта<input name="project_type" placeholder="Экологическая лаборатория" /></label>
          <label className="span2">Стиль контента<input name="content_style" placeholder="Экспертный B2B" /></label>
          {error && <p className="error span2">{error}</p>}
          <div className="formActions span2"><button type="button" className="button" onClick={() => setOpen(false)}>Отмена</button><button className="button primary" disabled={busy}>{busy ? "Сохраняю…" : "Добавить"}</button></div>
        </form>
      </div>
    </div>}
  </>;
}
