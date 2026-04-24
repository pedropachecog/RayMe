import createDOMPurify from 'dompurify';
import { marked } from 'marked';

const markdownTags = ['p', 'br', 'strong', 'em', 'code', 'pre', 'blockquote', 'ul', 'ol', 'li', 'a'];
const markdownAttributes = ['href', 'title'];
const allowedTags = new Set(markdownTags);
const dangerousRawTextTags = new Set(['script', 'style', 'iframe', 'object', 'embed', 'svg', 'math', 'template']);

export function renderTrustedMarkdown(untrustedMarkdown: string): string {
  const html = marked.parse(untrustedMarkdown, { async: false });
  const purifier = typeof window === 'undefined' ? createDOMPurify : createDOMPurify(window);

  const sanitized = purifier.sanitize(html, {
    ALLOWED_TAGS: markdownTags,
    ALLOWED_ATTR: markdownAttributes,
    ALLOW_DATA_ATTR: false,
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[/?#]|[^a-z+.-])/i
  });

  return enforceMarkdownAllowlist(sanitized);
}

function enforceMarkdownAllowlist(html: string): string {
  if (typeof document === 'undefined') return html;

  const template = document.createElement('template');
  template.innerHTML = html;
  cleanChildren(template.content);

  return template.innerHTML;
}

function cleanChildren(parent: ParentNode): void {
  for (const node of Array.from(parent.childNodes)) {
    if (node.nodeType === Node.COMMENT_NODE) {
      node.remove();
      continue;
    }

    if (node.nodeType === Node.ELEMENT_NODE) cleanElement(node as Element);
  }
}

function cleanElement(element: Element): void {
  const tagName = element.tagName.toLowerCase();

  if (!allowedTags.has(tagName)) {
    if (dangerousRawTextTags.has(tagName)) {
      element.remove();
      return;
    }

    cleanChildren(element);
    unwrapElement(element);
    return;
  }

  for (const attribute of element.getAttributeNames()) {
    const normalizedAttribute = attribute.toLowerCase();
    const allowed = tagName === 'a' && markdownAttributes.includes(normalizedAttribute);

    if (!allowed) element.removeAttribute(attribute);
  }

  if (tagName === 'a') {
    const href = element.getAttribute('href');
    if (href && !isSafeHref(href)) element.removeAttribute('href');
  }

  cleanChildren(element);
}

function unwrapElement(element: Element): void {
  const parent = element.parentNode;
  if (!parent) {
    element.remove();
    return;
  }

  while (element.firstChild) {
    parent.insertBefore(element.firstChild, element);
  }

  element.remove();
}

function isSafeHref(href: string): boolean {
  const normalizedHref = href.trim();
  if (normalizedHref.length === 0) return false;

  const protocolMatch = /^[a-z][a-z0-9+.-]*:/i.exec(normalizedHref);
  if (!protocolMatch) return true;

  return /^(https?|mailto):$/i.test(protocolMatch[0]);
}
