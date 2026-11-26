import Cocoa
import SingKhmerCore

/// The "Add Word…" window (Sing Khmer menu in the menu bar).
///
///   Spellings  kom tov, komtov        commas between alternatives
///   Khmer      កុំទៅ                   paste it, or type known words in Sing Khmer (check it)
///   → shows the Khmer that will be saved and any spelling that already means
///     something else; Add appends the lines to my_words.txt, live at once.
///
/// All the rules live in SingKhmerCore/WordForm.swift (tested on Linux); this file
/// only lays out controls.
final class AddWordWindow: NSObject, NSWindowDelegate, NSTextFieldDelegate {
    static let shared = AddWordWindow()

    private var window: NSWindow?
    private let spellingsField = NSTextField()
    private let khmerField = NSTextField()
    private let missedPopup = NSPopUpButton()
    private let previewLabel = NSTextField(labelWithString: "")
    private let notesLabel = NSTextField(wrappingLabelWithString: "")
    private let statusLabel = NSTextField(labelWithString: "")
    private let addButton = NSButton(title: "Add", target: nil, action: nil)

    func show() {
        let window = self.window ?? makeWindow()
        self.window = window
        fillMissed()
        if spellingsField.stringValue.isEmpty, let miss = Shared.store.lastMiss {
            spellingsField.stringValue = miss
        }
        statusLabel.stringValue = ""
        update()
        NSApp.activate(ignoringOtherApps: true)
        window.center()
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(spellingsField.stringValue.isEmpty ? spellingsField : khmerField)
    }

    // MARK: - Layout

    private func makeWindow() -> NSWindow {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 480, height: 300),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Add Word to Sing Khmer"
        window.level = .floating
        window.isReleasedWhenClosed = false
        window.delegate = self

        spellingsField.placeholderString = "kom tov, komtov"
        khmerField.placeholderString = "Paste Khmer, or type known words: bong srey"
        khmerField.font = NSFont.systemFont(ofSize: 16)
        for field in [spellingsField, khmerField] { field.delegate = self }

        missedPopup.target = self
        missedPopup.action = #selector(pickMissed(_:))
        previewLabel.font = NSFont.systemFont(ofSize: 22)
        notesLabel.textColor = .secondaryLabelColor
        notesLabel.font = NSFont.systemFont(ofSize: NSFont.smallSystemFontSize)
        statusLabel.textColor = .systemGreen

        addButton.target = self
        addButton.action = #selector(add(_:))
        addButton.keyEquivalent = "\r"
        addButton.bezelStyle = .rounded
        let closeButton = NSButton(title: "Close", target: self, action: #selector(close(_:)))
        closeButton.keyEquivalent = "\u{1b}"
        closeButton.bezelStyle = .rounded

        let grid = NSGridView(views: [
            [label("Spellings:"), spellingsField],
            [label("Khmer:"), khmerField],
            [label("Missed:"), missedPopup],
            [label("Saves:"), previewLabel],
        ])
        grid.column(at: 0).xPlacement = .trailing
        grid.rowSpacing = 10
        grid.column(at: 1).width = 340

        let buttons = NSStackView(views: [statusLabel, NSView(), closeButton, addButton])
        buttons.orientation = .horizontal
        let stack = NSStackView(views: [grid, notesLabel, buttons])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top: 20, left: 20, bottom: 20, right: 20)
        stack.translatesAutoresizingMaskIntoConstraints = false
        buttons.translatesAutoresizingMaskIntoConstraints = false

        let content = NSView()
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            stack.topAnchor.constraint(equalTo: content.topAnchor),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: content.bottomAnchor),
            buttons.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -40),
            notesLabel.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -40),
        ])
        window.contentView = content
        return window
    }

    private func label(_ text: String) -> NSTextField {
        NSTextField(labelWithString: text)
    }

    private func fillMissed() {
        missedPopup.removeAllItems()
        let missed = Shared.store.missedSpellings.prefix(30)
        missedPopup.addItem(withTitle: missed.isEmpty ? "(nothing missed yet)" : "Pick a missed spelling…")
        missedPopup.addItems(withTitles: Array(missed))
        missedPopup.isEnabled = !missed.isEmpty
    }

    // MARK: - Actions

    @objc private func pickMissed(_ sender: NSPopUpButton) {
        guard sender.indexOfSelectedItem > 0, let title = sender.titleOfSelectedItem else { return }
        spellingsField.stringValue = title
        sender.selectItem(at: 0)
        update()
        window?.makeFirstResponder(khmerField)
    }

    func controlTextDidChange(_ obj: Notification) {
        statusLabel.stringValue = ""
        update()
    }

    /// Recompute the preview, the warnings and whether Add is allowed.
    private func update() {
        let engine = Shared.store.engine
        let spellings = WordForm.spellings(spellingsField.stringValue)
        let khmer = WordForm.khmer(from: khmerField.stringValue, engine: engine)

        previewLabel.stringValue = khmer ?? ""
        var notes: [String] = []
        if !khmerField.stringValue.trimmingCharacters(in: .whitespaces).isEmpty && khmer == nil {
            notes.append("Can't make Khmer from that. Paste the Khmer, or use only words the keyboard knows.")
        }
        if !spellingsField.stringValue.trimmingCharacters(in: .whitespaces).isEmpty && spellings.isEmpty {
            notes.append("Spellings use letters only (a–z, space, '). Separate them with commas.")
        }
        if khmer != nil && !khmerField.stringValue.unicodeScalars.contains(where: Composer.isKhmer) {
            notes.append("Built from words the keyboard knows — check it is right before adding.")
        }
        if let khmer = khmer {
            notes += WordForm.notes(spellings: spellings, khmer: khmer, engine: engine)
        }
        notesLabel.stringValue = notes.joined(separator: "\n")
        addButton.isEnabled = khmer != nil && !spellings.isEmpty
    }

    @objc private func add(_ sender: Any?) {
        let spellings = WordForm.spellings(spellingsField.stringValue)
        guard let khmer = WordForm.khmer(from: khmerField.stringValue, engine: Shared.store.engine),
              !spellings.isEmpty else { return }
        do {
            let added = try Shared.store.addWords(spellings.map { UserWord(latin: $0, khmer: khmer) })
            statusLabel.textColor = .systemGreen
            statusLabel.stringValue = added
                ? "Added \(spellings.joined(separator: ", ")) → \(khmer). Works now."
                : "Already in your words."
            spellingsField.stringValue = ""
            khmerField.stringValue = ""
            fillMissed()
            update()
            window?.makeFirstResponder(spellingsField)
        } catch {
            statusLabel.textColor = .systemRed
            statusLabel.stringValue = "Could not save: \(error.localizedDescription)"
        }
    }

    @objc private func close(_ sender: Any?) {
        window?.orderOut(nil)
    }
}
