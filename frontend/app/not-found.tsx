import Link from "next/link";
export default function NotFound(){return <div className="errorScreen"><div className="errorCard"><span className="eyebrow">404</span><h1>Страница не найдена</h1><p>Возможно, ссылка устарела или раздел был перемещён.</p><Link className="button primary" href="/">На главную</Link></div></div>}
