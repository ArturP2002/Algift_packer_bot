// Сборщик товаров со страницы категории «Читай-города».
// Запуск: открыть категорию и нажать закладку из chitaigorod.bookmarklet.txt (или выполнить код в консоли).
// Закладка сама листает страницы кнопкой «Следующая» и останавливается на LIMIT товарах, на последней странице
// или по кнопке «Стоп и скачать». Импорт: python import_manual_products.py <файлы>.
(() => {
  const LIMIT = 600;
  const PAUSE_MS = 1500;
  const STALL_ROUNDS = 8;

  if (window.__cgCollector) {
    window.__cgCollector.finish();
    return;
  }

  const text = (root, selector) => {
    const el = root.querySelector(selector);
    return el ? el.textContent.replace(/\s+/g, " ").trim() : "";
  };
  const num = (value) => {
    const match = (value || "").replace(/[\s\u00a0]/g, "").match(/\d+(?:[.,]\d+)?/);
    return match ? Number(match[0].replace(",", ".")) : null;
  };

  const heading = text(document, "h1");
  // В названиях книг слова «книга» нет, а поиск смотрит и в категорию.
  const category = location.pathname.includes("/catalog/books") && !/книг/i.test(heading) ? `Книги: ${heading}` : heading;
  const items = new Map();

  const cards = () => document.querySelectorAll("article.product-card[data-testid-product-item]");
  const firstId = () => {
    const card = cards()[0];
    return card ? card.getAttribute("data-testid-product-item") : "";
  };

  const parse = () => {
    for (const card of cards()) {
      const id = card.getAttribute("data-testid-product-item");
      const link = card.querySelector("a.product-card__title");
      if (!id || !link) continue;
      const name = link.textContent.replace(/\s+/g, " ").trim();
      const author = text(card, ".product-card__subtitle");
      const title = (link.getAttribute("title") || (author ? `${name} (${author})` : name)).replace(/\s+/g, " ").trim();
      const price = num(text(card, ".product-mini-card-price__price"));
      if (!title || !price) continue;
      const stars = card.querySelector(".product-rating-mkt__stars");
      const actions = text(card, ".product-card__actions");
      const reviewsText = text(card, ".product-rating-mkt__reviews");
      const reviews = num(reviewsText);
      items.set(id, {
        store: "chitaigorod",
        id,
        title,
        author,
        cover: text(card, ".product-card__cover"),
        price,
        old_price: num(text(card, ".product-mini-card-price__old-price")),
        rating: stars ? num(stars.getAttribute("title")) : null,
        reviews: reviews && /тыс/i.test(reviewsText) ? Math.round(reviews * 1000) : reviews,
        in_stock: actions ? /купить/i.test(actions) : null,
        category,
        url: new URL(link.getAttribute("href"), location.origin).href.split("?")[0],
      });
    }
  };

  const panel = document.createElement("div");
  panel.style.cssText = "position:fixed;z-index:2147483647;right:16px;bottom:16px;padding:12px 14px;background:#111;color:#fff;font:14px/1.4 sans-serif;border-radius:10px;box-shadow:0 4px 16px rgba(0,0,0,.3)";
  const status = document.createElement("div");
  const stop = document.createElement("button");
  stop.textContent = "Стоп и скачать";
  stop.style.cssText = "margin-top:8px;padding:6px 10px;border:0;border-radius:6px;background:#2a7de1;color:#fff;cursor:pointer";
  panel.append(status, stop);
  document.body.appendChild(panel);

  let finished = false;
  let timer = null;

  const finish = () => {
    if (finished) return;
    finished = true;
    clearTimeout(timer);
    parse();
    panel.remove();
    delete window.__cgCollector;
    const payload = {
      store: "chitaigorod",
      category,
      source_url: location.href,
      collected_at: new Date().toISOString(),
      items: [...items.values()],
    };
    const slug = (heading || "category").toLowerCase().replace(/[^a-zа-я0-9]+/gi, "_").replace(/^_|_$/g, "");
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `chitaigorod_${slug}_${stamp}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    alert(`Читай-город: собрано ${payload.items.length} товаров из «${heading}»`);
  };

  stop.onclick = finish;
  window.__cgCollector = { finish };

  let pageId = "";
  let waited = 0;
  const step = () => {
    if (finished) return;
    const current = firstId();
    if (current === pageId) {
      waited += 1;
      if (waited >= STALL_ROUNDS) return finish();
      timer = setTimeout(step, PAUSE_MS);
      return;
    }
    pageId = current;
    waited = 0;
    parse();
    status.textContent = `Читай-город: собрано ${items.size} из ${LIMIT}…`;
    if (items.size >= LIMIT) return finish();
    const next = document.querySelector("a.chg-app-pagination__button-next");
    if (!next || next.getAttribute("aria-disabled") === "true" || next.classList.contains("chg-app-pagination__button--disabled")) return finish();
    next.scrollIntoView({ block: "center" });
    next.click();
    timer = setTimeout(step, PAUSE_MS);
  };
  step();
})();
