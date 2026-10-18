// Read-only check of a live Udemy course against the manifest from check_repo.py.
//
// Run in a logged-in Udemy instructor tab (any www.udemy.com page) with the
// browser's JavaScript tool. Paste this whole file, then on the last line call:
//
//     await udemyCheck(COURSE_ID, MANIFEST)
//
// where MANIFEST is the JSON object check_repo.py wrote. Returns a compact
// report object: {course, results: [[level, check, detail], ...], counts}.
// Never writes anything. Section numbers refer to udemy-practice-test-kit's
// UDEMY-PLATFORM-NOTES.md.

async function udemyCheck(courseId, manifest) {
  const AI = 'This course contains the use of artificial intelligence.';
  const results = [];
  const add = (level, check, detail = '') => results.push([level, check, String(detail).slice(0, 300)]);
  const api = async (path) => { const r = await fetch(path, {credentials: 'include'}); if (!r.ok) throw new Error(path + ' -> ' + r.status); return r.json(); };
  const strip = s => (s || '').replace(/<[^>]+>/g, ' ').replace(/&quot;/g, '"').replace(/&#x27;|&#39;/g, "'").replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim();
  const listing = manifest.listing || {};

  // ---- course / landing page -------------------------------------------
  const c = await api(`/api-2.0/courses/${courseId}/?fields[course]=title,headline,description,status_label,is_published,is_paid,price,locale,image_750x422,promo_asset,published_title&fields[asset]=title,status,length`);
  add('INFO', 'status', `${c.status_label}${c.published_title ? ' /course/' + c.published_title + '/' : ''}`);
  if (listing.title) add(c.title === listing.title ? 'PASS' : 'FAIL', 'title matches listing', c.title);
  if (listing.subtitle) add(c.headline === listing.subtitle ? 'PASS' : 'WARN', 'subtitle matches listing', c.headline);
  const desc = c.description || '';
  const aiNeeded = manifest.kind === 'video' || /AI-generated|text-to-speech|artificial intelligence/i.test(strip(desc));
  if (aiNeeded) add(strip(desc).startsWith(AI) ? 'PASS' : 'FAIL', 'description opens with the verbatim AI disclosure [21]', strip(desc).slice(0, 80));
  add(/<a\s/i.test(desc) ? 'FAIL' : 'PASS', 'no links in description');
  add((desc.match(/<li>/g) || []).length ? 'PASS' : 'WARN', 'description uses real bullets', (desc.match(/<li>/g) || []).length + ' list items');
  add(c.image_750x422 && !/placeholder|default/i.test(c.image_750x422) ? 'PASS' : 'FAIL', 'course image set', c.image_750x422 || 'none');
  add(c.promo_asset ? (c.promo_asset.status === 1 ? 'PASS' : 'WARN') : 'WARN', 'promo video', c.promo_asset ? `${c.promo_asset.title}, ${c.promo_asset.length}s, status ${c.promo_asset.status}` : 'none (optional)');
  add('INFO', 'price', `${c.price} (is_paid ${c.is_paid}), locale ${c.locale && (c.locale.locale || c.locale)}`);

  // ---- editor checklist ------------------------------------------------
  try {
    const m = JSON.parse((await api(`/api-2.0/courses/${courseId}/manage-menu/`)).menuJson);
    const all = Object.values(m.menu_list).flatMap(s => s.items);
    const open = all.filter(i => !i.completed && !/optional|Setup & test|Film & edit|Course feedback/i.test(i.title)).map(i => i.title);
    add(open.length ? 'WARN' : 'PASS', 'editor checklist complete (excluding optional/guide pages)', open.join(', '));
    const fb = all.find(i => /Course feedback/i.test(i.title));
    if (fb) add('INFO', 'reviewer feedback exists', fb.completed ? 'all items marked' : 'open items: read /manage/feedback/course');
  } catch (e) { add('WARN', 'editor checklist', e.message); }

  // ---- curriculum ------------------------------------------------------
  const items = (await api(`/api-2.0/courses/${courseId}/instructor-curriculum-items/?page_size=500&fields[chapter]=title&fields[quiz]=title,type,num_assessments&fields[lecture]=title,is_free,description,asset,supplementary_assets&fields[asset]=title,status,length,captions,asset_type&fields[caption]=locale_id,status,source,url`)).results;
  const chapters = items.filter(x => x._class === 'chapter'), lectures = items.filter(x => x._class === 'lecture'), quizzes = items.filter(x => x._class === 'quiz');
  add('INFO', 'curriculum', `${chapters.length} sections, ${lectures.length} lectures, ${quizzes.length} quizzes/tests`);

  if (manifest.kind === 'video') {
    const want = (listing.curriculum || []);
    if (want.length) {
      const got = items.filter(x => x._class !== 'quiz').map(x => (x._class === 'chapter' ? '#' : '') + x.title);
      const exp = want.map(x => (x.class === 'chapter' ? '#' : '') + x.title);
      const bad = exp.map((e, i) => e === got[i] ? null : `${i + 1}: want "${e}" got "${got[i]}"`).filter(Boolean);
      if (got.length !== exp.length) bad.unshift(`count ${got.length} vs listing ${exp.length}`);
      add(bad.length ? 'FAIL' : 'PASS', 'sections and lectures match the listing table, in order', bad.slice(0, 5).join('; '));
    }
    const last = lectures[lectures.length - 1];
    if (last && /bonus/i.test(last.title)) add(last.title === 'Bonus Lecture' ? 'PASS' : 'FAIL', "Bonus Lecture titled exactly 'Bonus Lecture' and last", last.title);
    // videos and captions
    const files = manifest.files || [];
    let total = 0; const vbad = [], cbad = [];
    for (let i = 0; i < lectures.length; i++) {
      const L = lectures[i], a = L.asset, f = files[i];
      if (!a || a.asset_type !== 'Video') { vbad.push(`${i + 1} no video`); continue; }
      total += a.length || 0;
      if (a.status !== 1) vbad.push(`${i + 1} status ${a.status}`);
      if (f && a.title !== f.mp4) vbad.push(`${i + 1} file ${a.title} (want ${f.mp4})`);
      const cap = (a.captions || []).find(x => (x.locale_id || '').startsWith('en'));
      if (!cap) { cbad.push(`${i + 1} no English caption`); continue; }
      if (f) {
        const txt = (await (await fetch(cap.url)).text()).replace(/\r/g, '');
        const cues = [...txt.matchAll(/-->[^\n]*\n([^\n]+)/g)].map(m => m[1]);
        if (cues.length !== f.cues || cues[0] !== f.first_cue) cbad.push(`${i + 1} caption ${cues.length} cues (want ${f.cues})`);
      }
    }
    add(vbad.length ? 'FAIL' : 'PASS', 'every lecture has its processed video (file names match the build)', vbad.slice(0, 6).join('; '));
    add(cbad.length ? 'FAIL' : 'PASS', 'every lecture has an English caption matching its local VTT', cbad.slice(0, 6).join('; '));
    add(total / 60 >= 30 ? 'PASS' : 'FAIL', 'runtime >= 30 min', (total / 60).toFixed(1) + ' min');
    if (!c.is_paid) add(total < 7200 ? 'PASS' : 'FAIL', 'free course under 2 hours [16]', (total / 60).toFixed(1) + ' min');
    if (manifest.runtime_seconds) add(Math.abs(total - manifest.runtime_seconds) < 30 ? 'PASS' : 'WARN', 'Udemy runtime matches the local build', `${total}s vs ${manifest.runtime_seconds}s`);
    // previews
    const free = lectures.map((L, i) => L.is_free ? i + 1 : null).filter(Boolean);
    add(free.length && free.length < lectures.length / 2 ? 'PASS' : 'FAIL', 'free previews are a few chosen lectures, not all [18]', `lectures ${free.join(', ') || 'none'}`);
    // promotion rules
    const descBad = lectures.map((L, i) => {
      const d = strip(L.description);
      if (!d) return null;
      if (/bonus/i.test(L.title)) return `${i + 1} Bonus Lecture has a description (reviewer removed a course list here) [21]`;
      if (/udemy\.com\/course|other courses|practice tests?/i.test(d)) return `${i + 1} promotional description`;
      return null;
    }).filter(Boolean);
    add(descBad.length ? 'FAIL' : 'PASS', 'no promotional lecture descriptions [17][21]', descBad.join('; '));
    const linksOutsideBonus = lectures.filter(L => !/bonus/i.test(L.title) && (L.supplementary_assets || []).some(s => s.asset_type === 'ExternalLink')).map(L => L.title);
    add(linksOutsideBonus.length ? 'WARN' : 'PASS', 'external links only in the Bonus Lecture', linksOutsideBonus.join('; '));
    // quizzes
    for (const q of quizzes) add(q.num_assessments > 0 ? 'PASS' : 'FAIL', `quiz has questions: ${q.title}`, q.num_assessments);
  }

  if (manifest.kind === 'practice-test') {
    const exams = manifest.exams || [];
    const tests = quizzes.filter(q => q.type === 'practice-test');
    add(tests.length === exams.length ? 'PASS' : 'FAIL', 'one practice test per exam', `${tests.length} on Udemy vs ${exams.length} in repo`);
    const F = 'fields[assessment]=prompt,correct_response,section';
    for (let i = 0; i < tests.length; i++) {
      const t = tests[i], e = exams[i];
      const live = (await api(`/api-2.0/quizzes/${t.id}/assessments/?page_size=250&${F}`)).results;
      const draft = (await api(`/api-2.0/quizzes/${t.id}/assessments/?page_size=250&draft=true&${F}`)).results;
      const key = a => strip(a.prompt.question) + '|' + JSON.stringify(a.correct_response) + '|' + a.section + '|' + a.prompt.answers.map(strip).join('#') + '|' + strip(a.prompt.explanation);
      const diffs = live.map((a, k) => draft[k] && key(a) === key(draft[k]) ? null : k + 1).filter(Boolean);
      add(live.length === draft.length && !diffs.length ? 'PASS' : 'FAIL', `${t.title}: live and draft identical [4]`, `live ${live.length}, draft ${draft.length}${diffs.length ? ', differ at ' + diffs.slice(0, 8).join(',') : ''}`);
      if (e) {
        add(live.length === e.questions ? 'PASS' : 'FAIL', `${t.title}: question count matches CSV`, `${live.length} vs ${e.questions}`);
        const letters = s => (s || '').split(',').map(n => 'abcdef'[+n - 1]).join(',');
        const kbad = live.map((a, k) => (a.correct_response || []).join(',') === letters(e.keys[k]) ? null : k + 1).filter(Boolean);
        add(kbad.length ? 'FAIL' : 'PASS', `${t.title}: answer keys match CSV`, kbad.slice(0, 10).join(','));
      }
    }
  }

  const counts = results.reduce((m, r) => (m[r[0]] = (m[r[0]] || 0) + 1, m), {});
  return {course: courseId, title: c.title, counts, results};
}
