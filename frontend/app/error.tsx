"use client";
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="errorScreen"><div className="errorCard"><span className="eyebrow">ContentDesk 1.0</span><h1>Что-то пошло не так</h1><p>{error?.message || "Неожиданная ошибка интерфейса."}</p><div className="headerActions"><button className="button primary" onClick={reset}>Попробовать снова</button><a className="button" href="/settings">Диагностика</a></div></div></div>;
}
