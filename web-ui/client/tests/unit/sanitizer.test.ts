import { describe, expect, it } from 'vitest';

import { renderTrustedMarkdown } from '../../src/lib/sanitizer/renderMarkdown';

describe('renderTrustedMarkdown', () => {
  it('removes dangerous card HTML and attributes', () => {
    const rendered = renderTrustedMarkdown(
      '<img src=x onerror=alert(1)>\n<script>alert(1)</script>\n<span data-card="x" style="color:red">styled</span>'
    );

    expect(rendered).not.toContain('<img');
    expect(rendered).not.toContain('onerror=alert(1)');
    expect(rendered).not.toContain('<script>alert(1)</script>');
    expect(rendered).not.toContain('<script');
    expect(rendered).not.toContain('data-card');
    expect(rendered).not.toContain('style=');
    expect(rendered).toContain('styled');
  });

  it('strips dangerous link protocols', () => {
    const rendered = renderTrustedMarkdown('[bad](javascript:alert(1)) [safe](https://example.test "Example")');

    expect(rendered).not.toContain('javascript:alert(1)');
    expect(rendered).not.toContain('href="javascript:');
    expect(rendered).toContain('<a href="https://example.test" title="Example">safe</a>');
  });

  it('preserves common Markdown prose formatting', () => {
    const rendered = renderTrustedMarkdown(
      [
        '**Bold** and *emphasis* with `code`.',
        '',
        '> A quoted line',
        '',
        '- one',
        '- two',
        '',
        '[RayMe](/gallery)'
      ].join('\n')
    );

    expect(rendered).toContain('<strong>Bold</strong>');
    expect(rendered).toContain('<em>emphasis</em>');
    expect(rendered).toContain('<code>code</code>');
    expect(rendered).toContain('<blockquote>');
    expect(rendered).toContain('<ul>');
    expect(rendered).toContain('<li>one</li>');
    expect(rendered).toContain('<a href="/gallery">RayMe</a>');
  });
});
