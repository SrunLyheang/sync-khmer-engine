import Cocoa
import InputMethodKit
import SingKhmerCore

/// Receives key presses for one text field and turns them into Khmer.
///
/// All of the typing rules live in SingKhmerCore.Composer (which is unit-tested). This
/// class only translates between macOS and the Composer: NSEvent -> Composer.Key, and
/// the Composer's state -> underlined text in the document plus the candidate window.
@objc(SingKhmerInputController)
final class SingKhmerInputController: IMKInputController {
    private let composer: Composer? = Shared.engine.map { Composer(engine: $0) }
    /// True while this controller has underlined (marked) text in the document.
    private var hasMarkedText = false

    private static let noRange = NSRange(location: NSNotFound, length: NSNotFound)

    // MARK: - Key handling

    override func handle(_ event: NSEvent!, client sender: Any!) -> Bool {
        guard let composer = composer,
              let event = event, event.type == .keyDown,
              let client = sender as? IMKTextInput else { return false }

        let preceding = composer.isComposing ? precedingIsKhmer(client) : nil
        let outcome = composer.handle(Self.key(for: event), precedingIsKhmer: preceding)

        if let text = outcome.commit {
            client.insertText(text, replacementRange: Self.noRange)   // replaces the marked text
            hasMarkedText = false
        }
        refresh(composer, client)
        return outcome.handled
    }

    /// Make the document and the candidate window show the Composer's current state.
    private func refresh(_ composer: Composer, _ client: IMKTextInput) {
        guard composer.isComposing else {
            if hasMarkedText {                     // backspaced the word away entirely
                client.setMarkedText("", selectionRange: NSRange(location: 0, length: 0),
                                     replacementRange: Self.noRange)
                hasMarkedText = false
            }
            Shared.panel.hide()
            return
        }
        let marked = composer.markedText
        let attributes: [NSAttributedString.Key: Any] = [
            .underlineStyle: NSUnderlineStyle.single.rawValue,
        ]
        client.setMarkedText(NSAttributedString(string: marked, attributes: attributes),
                             selectionRange: NSRange(location: (marked as NSString).length, length: 0),
                             replacementRange: Self.noRange)
        hasMarkedText = true

        var rect = NSRect.zero
        _ = client.attributes(forCharacterIndex: 0, lineHeightRectangle: &rect)
        Shared.panel.show(composer.candidates, selected: composer.selected, near: rect)
    }

    private static func key(for event: NSEvent) -> Composer.Key {
        let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if modifiers.contains(.command) || modifiers.contains(.control) { return .other }

        switch event.keyCode {
        case 36, 76: return .enter                                   // return, keypad enter
        case 49: return .space
        case 51: return .backspace
        case 53: return .escape
        case 48: return modifiers.contains(.shift) ? .previous : .next   // tab
        case 124, 125: return .next                                  // right, down
        case 123, 126: return .previous                              // left, up
        default: break
        }

        guard let characters = event.characters, characters.count == 1,
              let character = characters.first,
              let scalar = character.unicodeScalars.first else { return .other }
        // Control characters and the private-use codes macOS uses for function keys.
        if scalar.value < 0x20 || scalar.value == 0x7F || (0xF700...0xF8FF).contains(scalar.value) {
            return .other
        }
        return .character(character)
    }

    /// Whether the character just before the composed text is Khmer, read from the
    /// document. Returns nil when the app does not say (many do not), in which case the
    /// Composer falls back to remembering what it last inserted.
    private func precedingIsKhmer(_ client: IMKTextInput) -> Bool? {
        let marked = client.markedRange()
        let location = marked.location != NSNotFound ? marked.location : client.selectedRange().location
        guard location != NSNotFound, location > 0, location < Int.max / 2,
              let before = client.attributedSubstring(from: NSRange(location: location - 1, length: 1)),
              let scalar = before.string.unicodeScalars.last else { return nil }
        return Composer.isKhmer(scalar)
    }

    // MARK: - Session lifecycle

    /// The app wants the composition finished now (a click elsewhere, a focus change).
    override func commitComposition(_ sender: Any!) {
        guard let composer = composer else { return }
        if let text = composer.commitPending() {
            var target: IMKTextInput? = sender as? IMKTextInput
            if target == nil { target = self.client() }
            target?.insertText(text, replacementRange: Self.noRange)
        }
        composer.reset()
        hasMarkedText = false
        Shared.panel.hide()
    }

    override func deactivateServer(_ sender: Any!) {
        commitComposition(sender)
        super.deactivateServer(sender)
    }
}
