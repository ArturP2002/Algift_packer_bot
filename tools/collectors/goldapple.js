// Сборщик товаров со страницы категории «Золотого яблока».
// Запуск: открыть категорию и нажать закладку из goldapple.bookmarklet.txt (или выполнить код в консоли).
// Закладка сама прокручивает ленту, пока сайт подгружает товары, и останавливается на LIMIT товарах,
// в конце категории или по кнопке «Стоп и скачать». Импорт: python import_manual_products.py <файлы>.
(() => {
  const LIMIT = 600;
  const PAUSE_MS = 2000;
  const STALL_ROUNDS = 8;
  const CARD = 'article[class*="_ga-product-card-vertical_"]';

  if (window.__gaCollector) {
    window.__gaCollector.finish();
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
    for (const card of document.querySelectorAll(CARD)) {
      const link = card.querySelector("a[href]");
      const href = link ? link.getAttribute("href") || "" : "";
      const id = (href.match(/^\/(\d+)/) || [])[1];
      const brand = text(card, '[class*="product-card-name__brand"]');
      const name = text(card, '[class*="product-card-name__name"]');
      const type = text(card, '[class*="product-card-vertical__type"]');
      const priceMeta = card.querySelector('meta[itemprop="price"]');
      const price = priceMeta ? num(priceMeta.getAttribute("content")) : null;
      if (!id || !name || !price) continue;
      const units = [...card.querySelectorAll('[class*="product-card-units__option-text"]')].map((el) => el.textContent.trim());
      items.set(id, {
        store: "goldapple",
        id,
        title: [type, brand, name].filter(Boolean).join(" "),
        brand,
        product_type: type,
        price,
        price_from: /^от/.test(text(card, '[class*="price-row__item-actual"]')),
        old_price: num(text(card, '[class*="price-row__item-old"] [class*="_ga-price_"]')),
        units,
        rating: num(text(card, '[class*="product-rating__rating-value"]')),
        reviews: num(text(card, '[class*="product-rating__review-count-value"]')),
        category,
        url: new URL(href, location.origin).href.split("?")[0],
      });
    }
  };

  const panel = document.createElement("div");
  panel.style.cssText = "position:fixed;z-index:2147483647;right:16px;bottom:16px;padding:12px 14px;background:#111;color:#fff;font:14px/1.4 sans-serif;border-radius:10px;box-shadow:0 4px 16px rgba(0,0,0,.3)";
  const status = document.createElement("div");
  const stop = document.createElement("button");
  stop.textContent = "Стоп и скачать";
  stop.style.cssText = "margin-top:8px;padding:6px 10px;border:0;border-radius:6px;background:#c8df34;color:#111;cursor:pointer";
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
    delete window.__gaCollector;
    const payload = {
      store: "goldapple",
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
    link.download = `goldapple_${slug}_${stamp}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    alert(`Золотое яблоко: собрано ${payload.items.length} товаров из «${category}»`);
  };

  stop.onclick = finish;
  window.__gaCollector = { finish };

  let lastCount = -1;
  let stalled = 0;
  const step = () => {
    if (finished) return;
    parse();
    status.textContent = `Золотое яблоко: собрано ${items.size} из ${LIMIT}…`;
    if (items.size >= LIMIT) return finish();
    stalled = items.size === lastCount ? stalled + 1 : 0;
    lastCount = items.size;
    if (stalled >= STALL_ROUNDS) return finish();
    const retry = [...document.querySelectorAll('[class*="load-button-with-icon__button_retry"]')].pop();
    if (retry && stalled >= 2) retry.click();
    window.scrollTo(0, document.body.scrollHeight);
    timer = setTimeout(step, PAUSE_MS);
  };
  step();
})();
