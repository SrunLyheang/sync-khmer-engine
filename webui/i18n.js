/* Khmer / English switching, ported from the Chatle app's useI18nStore + LanguageSwitcher
 * (minus React and zustand — this app has no build step).
 *
 * Same contract as there: flat "namespace.key" strings, {var} interpolation, and a lookup
 * that falls back current language -> English -> the key itself, so a missing translation
 * degrades to something readable instead of blanking the UI.
 *
 * Static text is translated by marking up the HTML, never by building strings here:
 *   data-i18n="key"              -> element.textContent
 *   data-i18n-placeholder="key"  -> placeholder attribute
 *   data-i18n-aria="key"         -> aria-label attribute
 *   data-i18n-title="key"        -> title attribute
 * Every one of those assigns through textContent/setAttribute, so translations can never
 * become markup (see the invariant at the top of app.js).
 */
'use strict';

const SK_DICTS = {
  en: {
    'app.name': 'Sing Khmer',
    'app.tagline': 'Type Latin letters the way you chat, get proper Khmer script.',
    'lang.switch': 'Change language',

    'notice.title': 'We save what you type — tap to read why',
    'notice.what': 'This is a test app. What you type is saved — with no name, phone number or IP address — so we can learn how people really spell Khmer and improve the converter.',
    'notice.retention': 'Emails, links and long numbers are removed automatically, and messages are deleted after 90 days.',
    'notice.warn': "Please don't type passwords or anything private.",
    'notice.optout': "Don't save my text",

    'input.label': 'Type here',
    'input.placeholder': 'Type in Latin letters… try: nh sl bong',
    'input.hint': 'Space joins words · double space = a real space · type a word twice → ៗ',

    'output.label': 'Your Khmer',
    'output.placeholder': 'Khmer will appear here…',
    'output.copy': 'Copy',
    'output.clear': 'Clear',
    'output.converting': 'Converting…',

    'readings.title': 'Other readings',
    'words.title': 'Tap a word to change it',
    'words.noMatch': 'no match',
    'words.english': 'English: {word}',
    'words.englishHint': 'Keep this word in English instead of Khmer',
    'words.ask': "We don't know this word — what should it be?",
    'words.askPlaceholder': 'In Khmer…',
    'words.askAria': 'Khmer for {spelling}',

    'feedback.label': 'Missing a word?',
    'feedback.spelling': 'What you typed (e.g. nekna)',
    'feedback.khmer': 'The Khmer it should be (អ្នកណា)',
    'feedback.hint': 'This is the most useful thing you can do — it adds real words to the dictionary.',

    'common.send': 'Send',
    'common.sending': 'Sending…',
    'common.loading': 'Loading…',
    'common.thanks': 'Thank you!',
    'common.copied': 'Copied',
    'common.nothingToCopy': 'Nothing to copy',
    'common.copyManual': 'Press and hold the Khmer text to copy',
    'common.needSpelling': 'Type what you typed first',
    'common.needKhmerWord': 'Type the Khmer word',
    'common.needKhmer': 'Please type it in Khmer',
    'common.notSent': 'Could not send',
    'common.notStored': "Couldn't save it right now — please try again later",
  },

  km: {
    // The name stays in Latin script: it's what people search for.
    'app.name': 'Sing Khmer',
    'app.tagline': 'វាយអក្សរឡាតាំងតាមរបៀបដែលអ្នកឆាត ទទួលបានអក្សរខ្មែរត្រឹមត្រូវ។',
    'lang.switch': 'ប្ដូរភាសា',

    'notice.title': 'យើងរក្សាទុកអត្ថបទដែលអ្នកវាយ — ចុចដើម្បីអានបន្ថែម',
    'notice.what': 'នេះជាកម្មវិធីសាកល្បង។ អ្វីដែលអ្នកវាយត្រូវបានរក្សាទុក ដោយគ្មានឈ្មោះ លេខទូរស័ព្ទ ឬអាសយដ្ឋាន IP ទេ ដើម្បីឱ្យយើងដឹងពីរបៀបដែលមនុស្សសរសេរខ្មែរពិតប្រាកដ និងធ្វើឱ្យកម្មវិធីប្រសើរឡើង។',
    'notice.retention': 'អ៊ីមែល តំណភ្ជាប់ និងលេខវែងៗ ត្រូវបានលុបចេញដោយស្វ័យប្រវត្តិ ហើយសារត្រូវបានលុបក្រោយ ៩០ ថ្ងៃ។',
    'notice.warn': 'សូមកុំវាយពាក្យសម្ងាត់ ឬព័ត៌មានផ្ទាល់ខ្លួន។',
    'notice.optout': 'កុំរក្សាទុកអត្ថបទរបស់ខ្ញុំ',

    'input.label': 'វាយនៅទីនេះ',
    'input.placeholder': 'វាយជាអក្សរឡាតាំង… សាកល្បង៖ nh sl bong',
    'input.hint': 'ចន្លោះភ្ជាប់ពាក្យ · ចន្លោះពីរដង = ចន្លោះពិត · វាយពាក្យដដែលពីរដង → ៗ',

    'output.label': 'អក្សរខ្មែររបស់អ្នក',
    'output.placeholder': 'អក្សរខ្មែរនឹងបង្ហាញនៅទីនេះ…',
    'output.copy': 'ចម្លង',
    'output.clear': 'សម្អាត',
    'output.converting': 'កំពុងបម្លែង…',

    'readings.title': 'ការអានផ្សេងទៀត',
    'words.title': 'ចុចលើពាក្យដើម្បីប្ដូរ',
    'words.noMatch': 'រកមិនឃើញ',
    'words.english': 'អង់គ្លេស៖ {word}',
    'words.englishHint': 'រក្សាពាក្យនេះជាភាសាអង់គ្លេស ជំនួសឱ្យខ្មែរ',
    'words.ask': 'យើងមិនស្គាល់ពាក្យនេះទេ — តើវាគួរជាអ្វី?',
    'words.askPlaceholder': 'ជាភាសាខ្មែរ…',
    'words.askAria': 'អក្សរខ្មែរសម្រាប់ {spelling}',

    'feedback.label': 'បាត់ពាក្យមែនទេ?',
    'feedback.spelling': 'អ្វីដែលអ្នកបានវាយ (ឧ. nekna)',
    'feedback.khmer': 'ពាក្យខ្មែរដែលត្រឹមត្រូវ (អ្នកណា)',
    'feedback.hint': 'នេះជាអ្វីដែលមានប្រយោជន៍បំផុតដែលអ្នកអាចធ្វើបាន — វាបន្ថែមពាក្យពិតទៅក្នុងវចនានុក្រម។',

    'common.send': 'ផ្ញើ',
    'common.sending': 'កំពុងផ្ញើ…',
    'common.loading': 'កំពុងផ្ទុក…',
    'common.thanks': 'អរគុណ!',
    'common.copied': 'បានចម្លង',
    'common.nothingToCopy': 'គ្មានអ្វីត្រូវចម្លងទេ',
    'common.copyManual': 'ចុចឱ្យជាប់លើអក្សរខ្មែរដើម្បីចម្លង',
    'common.needSpelling': 'សូមវាយអ្វីដែលអ្នកបានវាយសិន',
    'common.needKhmerWord': 'សូមវាយពាក្យខ្មែរ',
    'common.needKhmer': 'សូមវាយជាភាសាខ្មែរ',
    'common.notSent': 'ផ្ញើមិនបានទេ',
    'common.notStored': 'រក្សាទុកមិនបានទេឥឡូវនេះ — សូមព្យាយាមម្ដងទៀត',
  },
};

const SK_LANGS = [
  { id: 'km', label: 'ខ្មែរ' },
  { id: 'en', label: 'EN' },
];

const SK_LANG_KEY = 'sk_lang';
const SK_DEFAULT_LANG = 'km';        // Khmer-first, like the Chatle app

window.SkI18n = (function () {
  const listeners = [];

  function stored() {
    try {
      const v = localStorage.getItem(SK_LANG_KEY);
      return SK_DICTS[v] ? v : SK_DEFAULT_LANG;
    } catch (e) {
      return SK_DEFAULT_LANG;         // private browsing blocks storage
    }
  }

  let lang = stored();

  /** Translate a key, interpolating {var} placeholders. Never returns undefined. */
  function t(key, vars) {
    let str = SK_DICTS[lang][key];
    if (str == null) str = SK_DICTS.en[key];
    if (str == null) str = key;
    if (vars) {
      Object.keys(vars).forEach((name) => {
        str = str.split('{' + name + '}').join(String(vars[name]));
      });
    }
    return str;
  }

  /** Translate everything marked up in the HTML. textContent/setAttribute only. */
  function apply() {
    document.documentElement.lang = lang;
    document.documentElement.setAttribute('data-lang', lang);
    const set = (attr, fn) => {
      document.querySelectorAll('[' + attr + ']').forEach((n) => {
        fn(n, t(n.getAttribute(attr)));
      });
    };
    set('data-i18n', (n, v) => { n.textContent = v; });
    set('data-i18n-placeholder', (n, v) => { n.setAttribute('placeholder', v); });
    set('data-i18n-aria', (n, v) => { n.setAttribute('aria-label', v); });
    set('data-i18n-title', (n, v) => { n.setAttribute('title', v); });
    listeners.forEach((fn) => fn(lang));
  }

  function setLang(next) {
    if (!SK_DICTS[next]) return;
    lang = next;
    try { localStorage.setItem(SK_LANG_KEY, next); } catch (e) { /* ignore */ }
    apply();
  }

  /** Two languages, so one button cycles — same as Chatle's LanguageSwitcher. */
  function toggle() {
    const i = SK_LANGS.findIndex((l) => l.id === lang);
    setLang(SK_LANGS[(i + 1) % SK_LANGS.length].id);
  }

  return {
    t,
    apply,
    setLang,
    toggle,
    langs: SK_LANGS,
    current: () => lang,
    /** Re-render dynamic content (word tiles, output) when the language changes. */
    onChange: (fn) => listeners.push(fn),
  };
})();
