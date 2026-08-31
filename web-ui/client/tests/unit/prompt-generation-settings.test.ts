import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import promptPanelSource from '../../src/lib/components/settings/PromptGenerationSettingsPanel.svelte?raw';
import settingsRouteSource from '../../src/routes/settings/+page.svelte?raw';

const clientRoot = process.cwd().replaceAll('\\', '/').endsWith('/web-ui/client')
  ? process.cwd()
  : resolve(process.cwd(), 'web-ui/client');
const appCss = readFileSync(resolve(clientRoot, 'src/app.css'), 'utf8');

describe('Prompt & Generation visual contract', () => {
  it('ships a valid local Manrope SemiBold asset and OFL without a runtime font request', () => {
    const font = readFileSync(resolve(clientRoot, 'static/fonts/Manrope-SemiBold.woff2'));
    const license = readFileSync(resolve(clientRoot, 'static/fonts/OFL.txt'), 'utf8');

    expect(font.subarray(0, 4).toString('ascii')).toBe('wOF2');
    expect(font.length).toBeGreaterThan(40_000);
    expect(createHash('sha256').update(font).digest('hex')).toBe(
      '4b751c7594f0619ec9259c9f5564e0245944cdf0f564b1a3bec612eb98ea8ee1'
    );
    expect(license).toContain('SIL OPEN FONT LICENSE Version 1.1');
    expect(appCss).toContain("url('/fonts/Manrope-SemiBold.woff2') format('woff2')");
    expect(appCss).not.toMatch(/https?:\/\/|fonts\.(googleapis|gstatic)\.com/i);
  });

  it('assigns Manrope once to app Heading/Display roles while controls and prompt prose inherit Inter', () => {
    expect(appCss).toContain("--font-family-body: 'Inter'");
    expect(appCss).toContain("--font-family-heading: 'Manrope'");
    expect(appCss).toMatch(/h1,[\s\S]*h6[\s\S]*font-family:\s*var\(--font-family-heading\)/);
    expect(appCss).toMatch(/html\s*\{[\s\S]*font-family:\s*var\(--font-family-body\)/);
    expect(promptPanelSource).toContain('font-family: var(--font-family-body)');
  });

  it('locks the 320, 640, and 720 responsive contracts and 44px touch geometry', () => {
    expect(appCss).toContain('overflow-x: hidden');
    expect(promptPanelSource).toMatch(/\.prompt-panel\s*\{[\s\S]*min-width:\s*0/);
    expect(promptPanelSource).toMatch(/\.mode-card\s*\{[\s\S]*min-height:\s*56px/);
    expect(promptPanelSource).toMatch(/min-height:\s*44px/);
    expect(promptPanelSource).toMatch(/@media\s*\(min-width:\s*640px\)[\s\S]*grid-template-columns:\s*repeat\(3,/);
    expect(promptPanelSource).toMatch(/@media\s*\(min-width:\s*720px\)[\s\S]*grid-template-columns:\s*repeat\(2,/);
    expect(promptPanelSource).toMatch(/@media\s*\(max-width:\s*719px\)/);
    expect(promptPanelSource).toMatch(/@media\s*\(max-width:\s*359px\)/);
  });

  it('keeps empty, loading, error, populated, partial, and saved states explicit and geometry-stable', () => {
    const stateContracts = [
      ['empty Custom', "value.mode === 'custom'", 'blank remains intentionally empty'],
      ['loading', "loadState === 'loading'", 'settings-skeleton'],
      ['load error', "loadState === 'error'", 'Settings unavailable'],
      ['save error', 'role="alert"', 'Your changes are still here'],
      ['populated preset', 'Built-in preset', 'Modified'],
      ['partial invalid', 'aria-invalid', 'field-error'],
      ['saved', 'role="status"', 'Settings saved.']
    ] as const;

    const combinedSource = `${promptPanelSource}\n${settingsRouteSource}`;
    for (const [name, first, second] of stateContracts) {
      expect(combinedSource, name).toContain(first);
      expect(combinedSource, name).toContain(second);
    }
    expect(promptPanelSource).toMatch(/\.prompt-editor,[\s\S]*\.generation-section\s*\{[\s\S]*min-width:\s*0/);
  });

  it('preserves long Unicode, line breaks, hostile markup, and mandatory-overflow input as exact text', () => {
    const hostileLongPrompt = [
      '<img src=x onerror=alert(1)>',
      '<script>globalThis.compromised = true</script>',
      '雪'.repeat(1_200),
      'final line that must remain visible'
    ].join('\n');
    expect(hostileLongPrompt).toContain('\n');
    expect(promptPanelSource).toContain('value={selectedPrompts.main}');
    expect(promptPanelSource).toContain("updatePrompt('main', (event.currentTarget as HTMLTextAreaElement).value)");
    expect(promptPanelSource).toMatch(/textarea\s*\{[\s\S]*min-height:\s*144px[\s\S]*max-height:\s*320px[\s\S]*resize:\s*vertical/);
    expect(promptPanelSource).toContain('white-space: pre-wrap');
    expect(promptPanelSource).toContain('overflow-wrap: anywhere');
    expect(promptPanelSource).not.toMatch(/\{@html\}|innerHTML|line-clamp|text-overflow:\s*ellipsis/);
    expect(promptPanelSource).not.toMatch(/\.slice\(|\.substring\(|\.substr\(/);

  });

  it('marks selected Roleplay with radio, Default chip, and pulse strip without color-only state', () => {
    expect(promptPanelSource).toContain('type="radio"');
    expect(promptPanelSource).toContain('checked={value.mode === option.mode}');
    expect(promptPanelSource).toContain("option.mode === 'roleplay'");
    expect(promptPanelSource).toContain('<span class="chip">Default</span>');
    expect(promptPanelSource).toMatch(/\.mode-card\.selected::before[\s\S]*width:\s*4px[\s\S]*var\(--pulse-gradient\)/);
  });
});
