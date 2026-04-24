import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

import appShellSource from '../../src/lib/components/AppShell.svelte?raw';

const forbiddenTopLevelLabels = ['Call', 'Account', 'Billing', 'Logout', 'Subscribe'];
const appCss = readFileSync('src/app.css', 'utf8');

function navigationLabels() {
  return [...appShellSource.matchAll(/label: '([^']+)', href: '([^']+)'/g)].map((match) => ({
    label: match[1],
    href: match[2]
  }));
}

describe('AppShell', () => {
  it('declares the approved True Dark tokens', () => {
    for (const token of [
      '#060e20',
      '#091328',
      '#141f38',
      '#192540',
      '#b6a0ff',
      '#00e3fd',
      '#dee5ff',
      '#9eaad5',
      '#ff716c'
    ]) {
      expect(appCss).toContain(token);
    }
  });

  it('uses exactly Home, Gallery, Voice Lab, and Settings as top-level destinations', () => {
    expect(navigationLabels()).toEqual([
      { label: 'Home', href: '/' },
      { label: 'Gallery', href: '/gallery' },
      { label: 'Voice Lab', href: '/voice-lab' },
      { label: 'Settings', href: '/settings' }
    ]);

    for (const label of forbiddenTopLevelLabels) {
      expect(appShellSource).not.toContain(label);
    }
  });

  it('renders the mobile bottom navigation from exactly four items', () => {
    expect(navigationLabels()).toHaveLength(4);
    expect(appShellSource).toContain('class="bottom-nav"');
    expect(appShellSource).toContain('{#each navigation as item}');
    expect(appShellSource).toContain('grid-template-columns: repeat(4, minmax(0, 1fr))');
    expect(appShellSource).toContain('min-height: 64px');
  });
});
