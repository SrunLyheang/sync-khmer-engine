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
> gives the same answer as the Python engine on 6,713 inputs). The three files that talk
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

| Key | What it does |
| --- | --- |
| Letters | Build up a word. It shows underlined, and a small list of candidates appears below it. |
| **Space** | Converts the word to the highlighted candidate (the first one unless you moved). |
| **1** to **9** | Picks that candidate directly. Use this for homophones: `jg` then `2`. |
| Arrow keys, **Tab** | Move the highlight through the list. |
| **Return** | Converts the word. It does not also send the message; press Return again to send. |
| **Esc** | Keeps the Latin exactly as you typed it. |
| **Delete** | Removes the last letter of the word you are typing. |
| Punctuation | Converts the word, then types the punctuation. |

Things worth knowing:

- **Spaces.** Khmer words are written without spaces between them, so the space that
  converts a Khmer word is not typed. Press space **twice** to get a real space. Words
  left in English keep their normal spaces.
- **No spaces needed.** `nhslbong` converts the same as `nh sl bong`.
- **English words** such as `hello` or `ok` are left alone. A word that is both, like
  `computer`, converts to Khmer and offers the English as a later candidate.
- **The last candidate is always what you typed**, so you can always keep the Latin.
- **Two-word spellings.** After a word that can start a two-word spelling (for example
  `msel` in `msel minh`), the word shows converted but stays underlined after the space.
  Keep typing; it settles on the next word. Return confirms it straight away.
- **Writing a lot of English?** Switch back to your normal keyboard (Ctrl+Space). A few
  short English words are also Sing Khmer spellings (`you`, `a`) and will convert.
- **Password fields** always bypass input methods. That is macOS, not a bug.

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

A healthy start prints `loaded 4581 spellings` (the number grows with the dictionary).
`engine_data.json is missing` means the build did not finish; run `./build.sh install`
again and read its output.

**After updating, it still behaves like the old version.**
Run `pkill -x SingKhmer`, then switch away from Sing Khmer and back.

**The candidate list appears in the wrong place.**
Some apps do not tell input methods where the cursor is; the list then appears at the
mouse pointer. Typing still works.

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
macos/SingKhmer/
  build.sh                        export + compile + assemble + install
  Package.swift                   Swift package (no Xcode project needed)
  Resources/Info.plist            tells macOS this app is an input method for Khmer
  Resources/icon.tiff             the menu bar icon
  Sources/SingKhmerCore/
    Engine.swift                  port of lookup.py: decode, readings, fuzzy matching
    Fuzzy.swift                   port of fuzzy.py
    Composer.swift                the typing rules (what each key does)
  Sources/SingKhmerIME/           the macOS shell
    main.swift                    starts the input method server
    InputController.swift         key press -> Composer -> text in the document
    CandidatePanel.swift          the floating candidate list
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

- Everything the engine cannot do yet applies here too: a two-word spelling typed with
  no space (`mselminh`) is not recognised, and no-space typing combined with a typo is
  weak.
- When several words are typed with no spaces, the list offers whole-phrase readings,
  not a choice for each word inside. Type the words separately to choose a homophone.
- Backspace after a word has been converted deletes Khmer characters; it does not turn
  the word back into Latin.
- The candidate list is keyboard-only; it cannot be clicked.
- The build is for your Mac only. Giving the app to someone else needs a paid Apple
  Developer account to sign and notarize it, or they build it themselves the same way.
