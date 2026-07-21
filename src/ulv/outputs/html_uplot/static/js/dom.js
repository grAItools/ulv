// Small DOM builder shared across views: create an element and set its
// class and text in one call. `className` is skipped when falsy; `text`
// is skipped when undefined (so `el("div")` builds a bare node).

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}
