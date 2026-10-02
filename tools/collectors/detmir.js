// Сборщик товаров со страницы категории «Детского мира».
// Запуск: открыть категорию и нажать закладку из detmir.bookmarklet.txt (или выполнить код в консоли).
// Закладка сама нажимает «Показать ещё» и останавливается на LIMIT товарах, когда кнопка пропала,
// или по кнопке «Стоп и скачать». Импорт: python import_manual_products.py <файлы>.
(() => {
  const LIMIT = 600;
  const PAUSE_MS = 2500;
  const STALL_ROUNDS = 6;

  if (window.__dmCollector) {
    window.__dmCollector.finish();
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

  const category = text(document, "h1");
  const items = new Map();

  const parse = () => {
    for (const card of document.querySelectorAll("section[data-product-id]")) {
      const id = card.dataset.productId;
      const link = card.querySelector('[data-testid="titleLink"]');
      const title = link ? link.textContent.replace(/\s+/g, " ").trim() : "";
      const priceBlock = card.querySelector('[data-testid="productPrice"]');
      const prices = priceBlock
        ? [...priceBlock.querySelectorAll("span")]
            .filter((el) => !el.closest('[data-testid="labelDiscount"]') && !el.children.length && /₽/.test(el.textContent))
            .map((el) => num(el.textContent))
        : [];
      if (!id || !title || !prices[0]) continue;
      items.set(id, {
        store: "detmir",
        id,
        title,
        price: prices[0],
        old_price: prices[1] || null,
        rating: num(text(card, '[data-testid="rating"] [data-testid="typography"]')),
        reviews: num(text(card, '[data-testid="reviewCount"]')),
        in_stock: !!card.querySelector('[data-testid="addToCartButton"]'),
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
    delete window.__dmCollector;
    const payload = {
      store: "detmir",
      category,
      source_url: location.href,
      collected_at: new Date().toISOString(),
      items: [...items.values()],
    };
    const slug = (category || "category").toLowerCase().replace(/[^a-zа-я0-9]+/gi, "_").replace(/^_|_$/g, "");
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `detmir_${slug}_${stamp}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    alert(`Детский мир: собрано ${payload.items.length} товаров из «${category}»`);
  };

  stop.onclick = finish;
  window.__dmCollector = { finish };

  let lastCount = -1;
  let stalled = 0;
  const step = () => {
    if (finished) return;
    parse();
    status.textContent = `Детский мир: собрано ${items.size} из ${LIMIT}…`;
    if (items.size >= LIMIT) return finish();
    stalled = items.size === lastCount ? stalled + 1 : 0;
    lastCount = items.size;
    const more = document.querySelector('[data-testid="showElse"]');
    if (!more || stalled >= STALL_ROUNDS) return finish();
    more.scrollIntoView({ block: "center" });
    more.click();
    timer = setTimeout(step, PAUSE_MS);
  };
  step();
})();
