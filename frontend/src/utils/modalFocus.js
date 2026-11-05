// Pila compartida para diálogos anidados y restauración independiente del orden
// de desmontaje. Se conserva el estado previo de cada hermano del portal.
const stack = [];
const originals = new Map();
let observer = null;
let bodyOverflow = null;

function restore(element, state) {
  for (const [attribute, value] of Object.entries(state)) {
    if (value === null) element.removeAttribute(attribute);
    else element.setAttribute(attribute, value);
  }
}
function synchronize() {
  const top = stack.at(-1);
  if (!top) {
    observer?.disconnect(); observer = null;
    for (const [element, state] of originals) restore(element, state);
    originals.clear();
    if (bodyOverflow !== null) document.body.style.overflow = bodyOverflow;
    bodyOverflow = null;
    return;
  }
  for (const [element, state] of originals) {
    if (!element.isConnected) { restore(element, state); originals.delete(element); }
  }
  for (const element of document.body.children) {
    if (element === top.layer) {
      if (originals.has(element)) restore(element, originals.get(element));
    } else {
      if (!originals.has(element)) originals.set(element, { inert: element.getAttribute('inert'), 'aria-hidden': element.getAttribute('aria-hidden') });
      element.setAttribute('inert', '');
      element.setAttribute('aria-hidden', 'true');
    }
  }
  document.body.style.overflow = 'hidden';
}
function visible(element, panel) {
  if (element.matches(':disabled') || element.closest('[inert],[hidden]')) return false;
  for (let node = element; node && panel.contains(node); node = node.parentElement) {
    const style = getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
  }
  const details = element.closest('details:not([open])');
  return !details || Boolean(details.querySelector('summary')?.contains(element));
}
function focusable(panel) {
  return [...panel.querySelectorAll('button, a[href], input:not([type="hidden"]), select, textarea, summary, [tabindex]')]
    .filter((element) => element.tabIndex >= 0 && visible(element, panel));
}
function focusInside(entry) {
  if (entry.panel.contains(document.activeElement)) return;
  const preferred = entry.panel.querySelector('[autofocus],[data-autofocus]');
  (preferred && visible(preferred, entry.panel) ? preferred : focusable(entry.panel)[0] || entry.panel).focus({ preventScroll: true });
}

export function activateModal(entry) {
  if (!stack.length) {
    bodyOverflow = document.body.style.overflow;
    observer = new MutationObserver(synchronize);
    observer.observe(document.body, { childList: true });
  }
  stack.push(entry);
  // Mover foco antes de ocultar su origen del árbol de accesibilidad.
  if (entry.layer.hasAttribute('inert')) entry.layer.removeAttribute('inert');
  focusInside(entry);
  synchronize();
  const onKey = (event) => {
    if (stack.at(-1) !== entry) return;
    if (event.key === 'Escape') {
      event.preventDefault(); event.stopPropagation(); entry.dismiss();
    } else if (event.key === 'Tab') {
      const items = focusable(entry.panel);
      const position = items.indexOf(document.activeElement);
      if (!items.length || position < 0 || (event.shiftKey ? position === 0 : position === items.length - 1)) {
        event.preventDefault();
        (items[event.shiftKey ? items.length - 1 : 0] || entry.panel).focus();
      }
    }
  };
  const onFocus = (event) => {
    if (stack.at(-1) === entry && !entry.panel.contains(event.target)) focusInside(entry);
  };
  const changes = new MutationObserver(() => { if (stack.at(-1) === entry) focusInside(entry); });
  changes.observe(entry.panel, { childList: true, subtree: true });
  document.addEventListener('keydown', onKey);
  document.addEventListener('focusin', onFocus);
  return () => {
    changes.disconnect();
    document.removeEventListener('keydown', onKey);
    document.removeEventListener('focusin', onFocus);
    const index = stack.indexOf(entry);
    if (index >= 0) stack.splice(index, 1);
    synchronize();
    queueMicrotask(() => {
      const top = stack.at(-1);
      if (entry.previous?.isConnected && (!top || top.panel.contains(entry.previous))) entry.previous.focus({ preventScroll: true });
      else if (top) focusInside(top);
      else document.querySelector('main h1[tabindex]')?.focus({ preventScroll: true });
    });
  };
}
