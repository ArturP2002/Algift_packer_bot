// Сборщик товаров со страницы категории М.Видео.
// Запуск: открыть категорию, при желании нажать «Показать ещё» нужное число раз,
// затем выполнить этот код в консоли браузера (или через закладку из mvideo.bookmarklet.txt).
// Результат скачивается JSON-файлом; импорт: python import_manual_products.py <файлы>.
(() => {
  // Карточки вне экрана имеют content-visibility: auto, у них пустой innerText — читаем textContent.
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
  for (const card of document.querySelectorAll('.products-list a[href*="/products/"]')) {
    const href = card.getAttribute("href") || "";
    const id = (href.match(/\/products\/(\d+)/) || [])[1];
    const brand = text(card, "mvid-product-title .brand");
    let title = text(card, "mvid-product-title");
    if (brand && title.startsWith(brand)) title = title.slice(brand.length).trim();
    const price = num(text(card, "mvid-sale-price"));
    if (!id || !title || !price) continue;
    items.set(id, {
      store: "mvideo",
      id,
      title,
      brand,
      price,
      old_price: num(text(card, "mvid-base-price")),
      rating: num(text(card, "mvid-rating span:not(.reviews-count)")),
      reviews: num(text(card, "mvid-rating .reviews-count")),
      category,
      url: new URL(href, location.origin).href.split("?")[0],
    });
  }

  const payload = {
    store: "mvideo",
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
  link.download = `mvideo_${slug}_${stamp}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  alert(`М.Видео: собрано ${payload.items.length} товаров из «${category}»`);
})();
