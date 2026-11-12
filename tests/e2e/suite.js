// End-to-end suite. Usage: node suite.js <url>
const { chromium } = require('playwright'); const fs = require('fs');
const URL = process.argv[2] || 'http://localhost:8601';
const T = 240000;   // generous: the server may be CPU-throttled
let pass = 0, fail = 0; const failures = [];
const check = (name, ok, extra = '') => { ok ? pass++ : (fail++, failures.push(name)); console.log((ok ? 'PASS ' : 'FAIL ') + name + (extra ? '  [' + extra + ']' : '')); };
(async () => { try {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1500, height: 950 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  const body = async () => (await p.locator('body').innerText()).replace(/\s+/g, ' ');
  const idle = async () => {   // settled = no stale elements, no running indicator, for 600 ms in a row
    await p.waitForTimeout(300);
    let calm = 0; const t0 = Date.now();
    while (calm < 3 && Date.now() - t0 < T) {
      const busy = await p.evaluate(() => !!document.querySelector('[data-stale="true"], [data-testid="stStatusWidget"], [data-testid="stSpinner"]'));
      calm = busy ? 0 : calm + 1; await p.waitForTimeout(200);
    }
  };
  const until = async (fn, ms = 90000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await fn()) return true; } catch (e) {} await p.waitForTimeout(300); } return false; };
  const total = async () => { const m = /TOTAL (\d+)\/30/i.exec(await body()); return m ? +m[1] : null; };
  const timed = async (label, fn) => { const t = Date.now(); await fn(); const s = ((Date.now() - t) / 1000).toFixed(1); console.log('      time ' + label + ': ' + s + 's'); return +s; };

  await timed('start screen', async () => { await p.goto(URL); await p.getByText(/01 · Upload/i).waitFor({ timeout: T }); });
  check('start screen shows stored-deck note', (await body()).includes('198 AI4ALL Ignite study decks'));

  await timed('upload 3 decks', async () => {
    await p.setInputFiles('input[type=file]', ['Original Unredacted Version.pdf', 'Fake_Unredacted_Deck.pdf', 'Heavy Deck.pdf']);
    await p.locator('.st-key-queue').waitFor({ timeout: T }); await p.locator('.viewer img').waitFor({ timeout: T }); await idle(); });
  check('queue shows 3 bubbles', (await p.locator('.st-key-queue button:visible').count()) === 3);
  let t = await body();
  check('deck 1 matched by content (stored scores + undo link)', t.includes('stored') || (await p.getByRole('button', { name: 'Not this deck?' }).count()) === 1);
  check('deck 1 total auto-filled', await until(async () => (await total()) === 25), String(await total()));

  const cite = p.locator('.st-key-cites_algorithm button:visible').nth(1);
  const bubbles = () => p.evaluate(() => [...document.querySelectorAll('[data-testid="stButton"] button')].filter(b => {
    const st = getComputedStyle(b, '::after'); return st.content !== 'none' && st.content !== 'normal' && st.visibility === 'visible' && +st.opacity > 0.5; })
    .map(b => getComputedStyle(b, '::after').content).concat([...document.querySelectorAll('[data-baseweb="tooltip"]')].map(e => e.innerText)));
  await cite.hover(); const tipOk = await until(async () => { const v = await bubbles(); return v.length === 1 && /Slide 5: /.test(v[0]); }, 15000);
  check('cited-slide hover shows what the AI saw', tipOk);
  await p.mouse.move(5, 5); await p.waitForTimeout(300);
  check('hover bubble disappears when the mouse leaves', (await bubbles()).length === 0);
  const cites = p.locator('.st-key-cites_algorithm button:visible');
  for (let i = 0; i < Math.min(await cites.count(), 3); i++) await cites.nth(i).click({ timeout: 5000 }).catch(() => {});
  await p.locator('.st-key-pnext button').click(); await idle(); await p.mouse.move(5, 5); await p.waitForTimeout(300);
  check('no bubbles left on screen after clicking cited slides and Next', (await bubbles()).length === 0);
  await p.locator('.st-key-pprev button').click(); await idle();
  await cite.click(); await idle();
  check('cited-slide chip jumps slide', await until(async () => /Slide 5 of 9/.test(await body())), /Slide \d+ of \d+/.exec(await body())?.[0]);
  await p.locator('.st-key-crit_algorithm .tip').nth(1).hover(); await p.waitForTimeout(400);
  check('AI reasoning appears on hover', await p.locator('.st-key-crit_algorithm .tip').nth(1).locator('.tipbox').evaluate(e => getComputedStyle(e).visibility === 'visible'));
  await p.locator('.st-key-crit_citations .tip').first().hover(); await p.waitForTimeout(400);
  check('rubric levels appear on hover', await p.locator('.st-key-crit_citations .tip').first().locator('.tipbox').evaluate(e => getComputedStyle(e).visibility === 'visible'));
  await p.mouse.wheel(0, 1200); await p.waitForTimeout(800);
  check('top bar stays visible when scrolled', await p.locator('.st-key-topbar').evaluate(e => { const r = e.getBoundingClientRect(); return r.top >= 0 && r.bottom <= window.innerHeight && r.top < 120; }));
  await p.mouse.wheel(0, -3000); await p.waitForTimeout(500);

  await p.getByRole('button', { name: '+', exact: true }).click(); await idle();
  check('zoom in to 150%', await until(async () => (await body()).includes('150%') && await p.locator('.viewer').evaluate(e => e.scrollWidth > e.clientWidth)));
  await p.getByRole('button', { name: '−', exact: true }).click(); await idle();
  check('zoom back to 100%', await until(async () => (await body()).includes('100%')));

  // deck 3 (heavy) → redacted view
  await p.locator('.st-key-queue button:visible').nth(2).click(); await idle();
  await timed('redacted view, heavy deck', async () => {
    await p.locator('[data-testid="stMain"] [data-testid="stButtonGroup"] button').filter({ hasText: 'Redacted' }).first().click();
    await p.getByText('Redacted view: this is what Claude sees').waitFor({ timeout: T }); await idle(); });
  check('redacted view renders', await p.locator('.viewer img').count() === 1 && /Removed: .*face/.test(await body()));
  await p.locator('[data-testid="stMain"] [data-testid="stButtonGroup"] button').filter({ hasText: 'Original' }).first().click(); await idle();

  // deck 2 → Claude dialog, paste with Ctrl+Enter
  await p.locator('.st-key-queue button:visible').nth(1).click(); await idle();
  check('deck 2 needs AI scores', await until(async () => (await body()).includes('no AI scores yet')));
  await timed('open Claude pop-up', async () => { await p.getByRole('button', { name: /Score with Claude/ }).click(); await p.locator('[role=dialog] textarea').waitFor({ timeout: T }); await idle(); });
  check('pop-up shows redaction summary', /Removed: .*name/.test(await body()));
  check('pop-up offers redacted download', (await p.locator('[role=dialog]').getByRole('button', { name: /submission-\d+\.pdf/ }).count()) === 1);
  const ta = p.locator('[role=dialog] textarea').last();
  await ta.fill(fs.readFileSync('reply.json', 'utf8')); await ta.press('Control+Enter');
  await p.locator('[role=dialog]').waitFor({ state: 'detached', timeout: T }).catch(() => {}); await idle();
  check('Ctrl+Enter loads reply and closes pop-up', await until(async () => (await p.locator('[role=dialog]').count()) === 0 && (await total()) === 29), String(await total()));

  // change a score, check persistence across decks
  const inp = p.locator('.st-key-crit_citations input').first(); await inp.click(); await p.keyboard.press('ArrowUp'); await p.keyboard.press('Enter'); await idle();
  check('changing a score updates total', await until(async () => (await total()) === 28), String(await total()));
  await p.getByRole('button', { name: /Previous/ }).click(); await idle();
  await p.getByRole('button', { name: /^Next/ }).click(); await idle();
  check('changed score survives navigation', await until(async () => /DECK 2 OF 3/i.test(await body()) && (await total()) === 28), String(await total()));

  // confirm with warning
  await p.getByPlaceholder('Your initials').fill('JD'); await p.getByPlaceholder('Your initials').press('Enter'); await idle();
  await p.getByRole('button', { name: /^Confirm/ }).click(); await p.getByText('Before you confirm', { exact: true }).waitFor({ timeout: T });
  const foxRight = await p.locator('[role=dialog] img').evaluate(e => e.getBoundingClientRect().left > window.innerWidth / 2);
  check('review warning shows, graphic on the right', foxRight);
  await p.getByRole('button', { name: /I've checked them/ }).click(); await idle();
  check('confirm moves to next deck', await until(async () => /DECK 3 OF 3/i.test(await body())));
  check('sidebar shows 1 of 3 confirmed', await until(async () => (await body()).includes('1 of 3 confirmed')));

  // prefill on deck 3, then gradebook
  await p.getByRole('button', { name: 'Prefill 5s' }).click(); await idle();
  check('prefill sets 30/30', await until(async () => (await total()) === 30), String(await total()));
  await p.getByText(/Gradebook and export/).click(); await idle();
  check('gradebook table has 3 rows', await until(async () => (await p.locator('table.gb tbody tr').count()) === 3));
  check('CSV download offered', await until(async () => (await p.getByRole('button', { name: /Download 1 confirmed/ }).count()) === 1));

  // undo a content match
  await p.locator('.st-key-queue button:visible').nth(0).click(); await idle();
  await p.getByRole('button', { name: 'Not this deck?' }).click(); await idle();
  check('"Not this deck?" removes stored scores', await until(async () => (await body()).includes('no AI scores yet')));

  // zip upload from the sidebar
  await timed('zip upload', async () => { await p.locator('section[data-testid="stSidebar"] input[type=file]').setInputFiles('two_decks.zip'); await p.waitForFunction(() => document.querySelectorAll('.st-key-queue button').length >= 5, null, { timeout: T }); await idle(); });
  check('zip adds 2 decks to the queue', (await p.locator('.st-key-queue button:visible').count()) === 5);

  // API mode asks for a key and rejects a bad one
  await p.locator('section[data-testid="stSidebar"] [data-testid="stButtonGroup"] button').filter({ hasText: 'API' }).click();
  await p.getByText('Switch to API mode').waitFor({ timeout: T });
  await p.getByPlaceholder('sk-ant-...').fill('not-a-key'); await p.getByRole('button', { name: 'Connect' }).click(); await p.getByText("doesn't look like an Anthropic API key").waitFor({ timeout: T }).catch(() => {});
  check('API pop-up rejects a bad key', await until(async () => (await body()).includes("doesn't look like an Anthropic API key")));
  await p.getByRole('button', { name: 'Stay in Free mode' }).click(); await idle();

  t = await body();
  const fetchErr = errs.filter(e => /Failed to fetch|preload CSS|dynamically imported/i.test(e));
  check('no app errors on page', !/Traceback|StreamlitAPIException|Error running app/.test(t));
  check('no "Failed to fetch" / preload errors', fetchErr.length === 0, fetchErr.slice(0, 2).join(' | '));
  check('no browser page errors', errs.length === 0, errs.slice(0, 2).join(' | '));
  console.log(`\n${pass} passed, ${fail} failed` + (fail ? ': ' + failures.join('; ') : ''));
  await b.close(); process.exit(fail ? 1 : 0);
 } catch (e) { console.log('CRASH ' + e.message.split('\n')[0]); console.log(pass + ' passed, ' + (fail + 1) + ' failed'); process.exit(1); } })();
