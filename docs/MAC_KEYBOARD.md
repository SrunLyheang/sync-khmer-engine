# Sing Khmer on your Mac

A macOS input method: you pick **Sing Khmer** from the keyboard menu in the menu bar, type
romanized Khmer in any app, and it becomes Khmer script as you go.

```
you type:   nh srolanh bong
you get:    ខ្ញុំស្រឡាញ់បង
```

It runs entirely on your Mac. There is no server, no account and no network access; the
dictionary is exported from `data/vocabulary.csv` when you build.

> **Status: the app has not been built on a Mac yet.** It was written in a Linux session.
> The engine port and the typing rules were compiled and tested there (the Swift decoder
> gives the same answer as the Python engine on about 6,800 inputs). The three files that talk
> to macOS (`Sources/SingKhmerIME/`) could only be syntax-checked, because Apple's
> frameworks do not exist on Linux. Expect that the first build may stop on a compile
> error in one of those files, or that something like the candidate window's position
> needs adjusting. If so, copy the error and send it over; see
> [If the build fails](#if-the-build-fails).

## What you need

- A Mac running macOS 11 or later.
- Xcode Command Line Tools (free, about 2 GB). They provide both `swift` and `python3`.
- This repository cloned on the Mac.

You do **not** need the full Xcode app, an Apple Developer account, or the App Store.

## Install

### 1. Install the command line tools

Open Terminal and run:

```bash
xcode-select --install
```

A window appears; click **Install** and wait for it to finish. If it says the tools are
already installed, carry on.

### 2. Get the code

If you already have the repository on your Mac:

```bash
cd path/to/sing-khmer-engine
git fetch origin
git checkout claude/khmer-romanizer-input-method-27ycxu
git pull
```

(Once this branch is merged, `git checkout master && git pull` instead.)

### 3. Build and install

```bash
cd macos/SingKhmer
./build.sh install
```

This exports the dictionary, compiles the app (a minute or two the first time), and
copies `SingKhmer.app` into `~/Library/Input Methods`. It ends by printing the next steps.

### 4. Log out and back in

Apple menu > **Log Out**, then log in again. macOS only looks for new input methods at
login. You only need this the first time.

### 5. Turn it on

1. Open **System Settings > Keyboard**.
2. Next to **Input Sources**, click **Edit...**.
3. Click **+** at the bottom left.
4. Choose **Khmer** in the language list (or type `Sing` in the search box).
5. Select **Sing Khmer** and click **Add**.

While you are there, switch on **Show Input menu in menu bar** so you can see which
keyboard is active.

On macOS 12 or older the same thing is in **System Preferences > Keyboard > Input Sources**.

### 6. Try it

Open TextEdit or Notes, switch to Sing Khmer from the menu bar (the icon is a small
**SK**), and type `nh srolanh bong` followed by a space.

To switch keyboards quickly, use **Ctrl+Space** or the **Globe** key.

## How to type

It works like a Chinese pinyin keyboard: you type Latin letters, a numbered row of Khmer
candidates appears under them, and you take one.

| Key | What it does |
| --- | --- |
| Letters | Build up a word. It shows underlined, with the candidate row below it. |
| **Space** | Takes the highlighted candidate (the first one unless you moved). |
| **1** to **9** | Takes that candidate directly. Use this for homophones: `jg` then `2`. |
| Arrow keys, **Tab** | Move the highlight along the row. |
| **Return** | Keeps the Latin exactly as you typed it. |
| **Esc** | Cancels: throws away the letters you were typing. |
| **Delete** | Removes the last letter. Pressed right after a word converted, it undoes the conversion (see below). |
| Punctuation | Takes the first candidate, then types the punctuation. |

Things worth knowing:

- **Spaces.** Khmer words are written without spaces between them, so the space that
  takes a Khmer candidate is not typed. Press space **twice** to get a real space. Words
  left in English keep their normal spaces.
- **No spaces needed.** `nhslbong` converts the same as `nh sl bong`. When you type
  several words run together, the row shows the whole phrase first and then choices for
  just the **first word**. Taking one of those converts that word and leaves the rest
  still being typed, so you can choose a homophone in the middle of a phrase.
- **Undo.** If a word converts to the wrong thing, press **Delete** straight away: the
  Khmer is removed and your Latin letters come back, ready to fix or to pick a different
  candidate. This only works as the very next key, and only in apps that let the
  keyboard read the text before the cursor (most do; where they do not, Delete just
  deletes as usual).
- **English words** such as `hello` or `ok` are left alone. A word that is both, like
  `computer`, converts to Khmer and offers the English as a later candidate.
- **The Latin you typed is always in the row** (normally last), and Return always keeps it.
- **Sending a message.** Return only sends once nothing is underlined. Normally you end
  a word with space, so one Return sends as usual.
- **Words that belong together.** A few two-word spellings only come out right if both
  words are looked up together (`bong rean` is one Khmer word, not two). After the first
  of those, the word shows converted but stays underlined after the space until the next
  word settles it.
- **Password fields** always bypass input methods. That is macOS, not a bug.

## It learns from you

Everything it learns stays in three small files on your Mac, in
`~/Library/Application Support/SingKhmer`. Click the **SK** icon in the menu bar to reach
them.

**Your choices.** It remembers which candidate you take for each spelling. The first time
you pick an alternative it becomes the first choice. Once you have a habit, one odd pick
does not change it, but picking the same alternative twice in a row does. If you keep a
word in Latin (Return), it learns that too, so `you` can stay English. Stored in
`history.json`.

**Your own words.** Menu: **Edit My Words...** opens `my_words.txt`. Add one word per
line, the spelling and then the Khmer:

```
jrern ច្រើន
ot ey អត់អី
```

Save the file; the next word you type uses it. Your words always come first for their
spelling, work inside run-together typing, and can add a new spelling for a word the
dictionary already has. To write the Khmer you can paste it, use Apple's Khmer keyboard,
or build it with Sing Khmer itself.

**What is missing.** Menu: **Show Missed Words** opens `missed_words.txt`: every spelling
you typed that matched nothing and was not English, most typed first. This is the short
list of words actually worth adding, so you fill in the dictionary from your real typing
instead of from a long list. A word disappears from it once you have taught it.

**Sharing what you taught it.** Your words only exist on your Mac until you merge them
into the project's dictionary:

```bash
python3 scripts/import_mac_words.py --dry-run   # see what would change
python3 scripts/import_mac_words.py             # write it to data/vocabulary.csv
git diff data/vocabulary.csv                    # review, then commit
```

After that the web app has them too.

## Updating

After you change `data/vocabulary.csv`, or pull new code:

```bash
cd macos/SingKhmer
./build.sh install
```

Then switch to another keyboard and back to Sing Khmer so the new version loads. No
logout is needed for updates.

## Checking the engine without installing

From `macos/SingKhmer`:

```bash
python3 ../../scripts/export_mac_data.py --data-only
swift run sk nh srolanh bong
```

This runs the same Swift engine the keyboard uses and prints the result with the
candidates for each word. Terminal often draws Khmer badly; paste the output into
TextEdit to see it properly. If a word is wrong here, the cause is the dictionary or the
engine, not the keyboard.

To run the full comparison against the Python engine:

```bash
./build.sh test
```

This needs the full Xcode app on most Macs (the Command Line Tools alone do not include
the test framework). It is optional; the same tests have already been run on Linux.

## Troubleshooting

**Sing Khmer is not in the Input Sources list.**
Log out and back in (step 4). Check the app is there: `ls ~/Library/Input\ Methods`.
In the **+** dialog, try the search box, and look under both **Khmer** and **Others**.

**It is selected, but letters come out as plain English.**
The app did not start or could not load its dictionary. Watch its log while you switch
to it and type:

```bash
log stream --predicate 'process == "SingKhmer"'
```

A healthy start prints `loaded 4658 spellings` (the number grows with the dictionary).
`engine_data.json is missing` means the build did not finish; run `./build.sh install`
again and read its output.

**After updating, it still behaves like the old version.**
Run `pkill -x SingKhmer`, then switch away from Sing Khmer and back.

**The candidate list appears in the wrong place.**
Some apps do not tell input methods where the cursor is; the list then appears at the
mouse pointer. Typing still works.

**Writing a lot of English is awkward.**
Switch back to your normal keyboard with Ctrl+Space. A few short English words are also
Sing Khmer spellings (`you`, `a`); they convert until you have kept them in Latin a couple
of times.

**Khmer shows as empty boxes.**
The app you are typing in is using a font with no Khmer letters. macOS includes Khmer
fonts (Khmer Sangam MN, Khmer MN), so this is rare; choose one of them in that app.

**A stray space appears, or a space is missing, between Khmer and an English word.**
The keyboard asks the app what character comes before the cursor to decide this, and
some apps answer wrongly or not at all. Note which app it happened in.

### If the build fails

`./build.sh install` stops at the first error and prints it. The useful part is the lines
containing `error:`, with the file name and line number just before them. Send those
lines over. Errors are most likely in `Sources/SingKhmerIME/`, the only code that could
not be compiled before reaching your Mac.

If the error is in the export step instead, check that Python can run the engine at all:
`python3 scripts/convert.py nh` from the repository root.

## Uninstall

1. **System Settings > Keyboard > Input Sources > Edit...**, select Sing Khmer, click **-**.
2. Run `./build.sh uninstall` from `macos/SingKhmer`.

## How it is put together

```
scripts/export_mac_data.py        Python: writes the dictionary file the app bundles
scripts/import_mac_words.py       Python: merges words you taught the keyboard into vocabulary.csv
macos/SingKhmer/
  build.sh                        export + compile + assemble + install
  Package.swift                   Swift package (no Xcode project needed)
  Resources/Info.plist            tells macOS this app is an input method for Khmer
  Resources/icon.tiff             the menu bar icon
  Sources/SingKhmerCore/
    Engine.swift                  port of lookup.py: decode, readings, fuzzy matching
    Fuzzy.swift                   port of fuzzy.py
    Composer.swift                the typing rules (what each key does)
    Learning.swift                your own words, your pick history, the missed-word list
  Sources/SingKhmerIME/           the macOS shell
    main.swift                    starts the input method server
    InputController.swift         key press -> Composer -> text in the document
    CandidatePanel.swift          the floating candidate row
    UserStore.swift               reads and writes the three learned-data files
  Sources/SingKhmerCLI/main.swift the `sk` command used above
  Tests/SingKhmerCoreTests/       Swift vs. Python comparison, and typing-rule tests
```

Only the part of the engine that depends on live typing was ported to Swift. Loading
the vocabulary, splitting Khmer into syllables, generating spelling variants and
building the lookup table all still happen in Python, at build time.

**If you change `src/sing_khmer_engine/lookup.py` or `fuzzy.py`,** make the same change
in `Engine.swift` or `Fuzzy.swift`, then run `./build.sh test`. The comparison test
replays thousands of inputs through both and fails if they disagree. Changes to the
vocabulary, the romanizer or the reverse index need no Swift changes at all; just
rebuild.

## Known limits

- No-space typing combined with a typo is weak (an engine limit, the same on the web app).
- Undo covers only the most recent word, and only as the very next key.
- Learning is per spelling. It does not yet use the words around it to choose between
  homophones.
- The candidate row is keyboard-only; it cannot be clicked.
- The build is for your Mac only. Giving the app to someone else needs a paid Apple
  Developer account to sign and notarize it, or they build it themselves the same way.
