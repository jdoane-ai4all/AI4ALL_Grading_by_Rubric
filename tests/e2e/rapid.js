// Rapid clicking: fire slide/deck changes faster than the server can finish each run.
const { chromium } = require('playwright');
const URL = process.argv[2];
(async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1500, height: 950 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(URL); await p.getByText(/01 · Upload/i).waitFor({ timeout: 240000 });
  await p.setInputFiles('input[type=file]', ['Heavy Deck.pdf', 'Fake_Unredacted_Deck.pdf']); await p.locator('.viewer img').waitFor({ timeout: 240000 });
  for (let i = 0; i < 12; i++) { await p.getByRole('button', { name: '›' }).click({ force: true, timeout: 5000 }).catch(() => {}); await p.waitForTimeout(120); }
  for (let i = 0; i < 6; i++) { await p.locator('.st-key-queue button:visible').nth(i % 2).click({ force: true, timeout: 5000 }).catch(() => {}); await p.waitForTimeout(150); }
  await p.locator('[data-testid="stMain"] [data-testid="stButtonGroup"] button').filter({ hasText: 'Redacted' }).first().click({ force: true }).catch(() => {});
  await p.waitForTimeout(500);
  await p.locator('.st-key-queue button:visible').nth(0).click({ force: true }).catch(() => {});
  await p.getByText('Redacted view: this is what Claude sees').waitFor({ timeout: 240000 }).catch(() => {});
  const ok = (await p.locator('.viewer img').count()) === 1 && !(await p.locator('body').innerText()).includes('Traceback');
  console.log('rapid clicking: ' + (ok ? 'PASS' : 'FAIL') + ' | page errors: ' + errs.length);
  await b.close(); process.exit(ok ? 0 : 1); })();
