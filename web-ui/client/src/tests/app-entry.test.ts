import { describe, expect, it } from 'vitest';
import pageSource from '../routes/+page.svelte?raw';

describe('RayMe app entry scaffold', () => {
  it('renders the operational home entry copy', () => {
    expect(pageSource).toContain('RayMe');
    expect(pageSource).toContain('Recent threads');
    expect(pageSource).toContain('Start Chat');
  });
});
