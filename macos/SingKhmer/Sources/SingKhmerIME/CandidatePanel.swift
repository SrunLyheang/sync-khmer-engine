import Cocoa

/// The small floating list of candidates shown under the word being typed.
///
/// It is drawn by this app rather than with InputMethodKit's IMKCandidates so that the
/// highlight and the number keys are driven by one piece of state (the Composer).
/// The window never becomes key or active, so it cannot take focus from the app being
/// typed into.
final class CandidatePanel {
    private let panel: NSPanel
    private let background: NSVisualEffectView
    private let label: NSTextField
    private let padding: CGFloat = 8
    private let gap: CGFloat = 4

    init() {
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 160, height: 40),
                        styleMask: [.borderless, .nonactivatingPanel],
                        backing: .buffered,
                        defer: true)
        panel.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.popUpMenuWindow)) + 1)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.hidesOnDeactivate = false          // this app is never the active app
        panel.isFloatingPanel = true
        panel.ignoresMouseEvents = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        background = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: 160, height: 40))
        background.material = .popover
        background.blendingMode = .behindWindow
        background.state = .active
        background.wantsLayer = true
        background.layer?.cornerRadius = 7
        background.layer?.masksToBounds = true
        background.autoresizingMask = [.width, .height]

        label = NSTextField(labelWithString: "")
        label.maximumNumberOfLines = 0
        label.lineBreakMode = .byClipping
        background.addSubview(label)
        panel.contentView = background
    }

    /// Show `candidates` (one per line, numbered) with `selected` highlighted, just
    /// below `rect`, which is where the composed text sits on screen.
    func show(_ candidates: [String], selected: Int, near rect: NSRect) {
        guard !candidates.isEmpty else {
            hide()
            return
        }
        let text = attributedList(candidates, selected: selected)
        let measured = text.boundingRect(with: NSSize(width: 4000, height: 4000),
                                         options: [.usesLineFragmentOrigin, .usesFontLeading])
        let textSize = NSSize(width: ceil(measured.width) + 8, height: ceil(measured.height) + 4)
        let size = NSSize(width: textSize.width + padding * 2, height: textSize.height + padding * 2)

        label.attributedStringValue = text
        label.frame = NSRect(x: padding, y: padding, width: textSize.width, height: textSize.height)

        // Some apps do not report where the text is; fall back to the mouse pointer.
        var anchor = rect
        if anchor.origin == .zero && anchor.size == .zero {
            anchor = NSRect(origin: NSEvent.mouseLocation, size: .zero)
        }
        let screen = NSScreen.screens.first { $0.frame.contains(anchor.origin) } ?? NSScreen.main
        var origin = NSPoint(x: anchor.minX, y: anchor.minY - size.height - gap)
        if let visible = screen?.visibleFrame {
            origin.x = max(visible.minX, min(origin.x, visible.maxX - size.width))
            if origin.y < visible.minY {                    // no room below: go above
                origin.y = min(anchor.maxY + gap, visible.maxY - size.height)
            }
        }
        panel.setFrame(NSRect(origin: origin, size: size), display: true)
        panel.orderFront(nil)
    }

    func hide() {
        panel.orderOut(nil)
    }

    private func attributedList(_ candidates: [String], selected: Int) -> NSAttributedString {
        let font = NSFont.systemFont(ofSize: 16)
        let numberFont = NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = 3
        let out = NSMutableAttributedString()
        for (i, candidate) in candidates.enumerated() {
            let isSelected = i == selected
            var numberAttrs: [NSAttributedString.Key: Any] = [
                .font: numberFont,
                .foregroundColor: NSColor.secondaryLabelColor,
                .paragraphStyle: paragraph,
            ]
            var textAttrs: [NSAttributedString.Key: Any] = [
                .font: font,
                .foregroundColor: NSColor.labelColor,
                .paragraphStyle: paragraph,
            ]
            if isSelected {
                numberAttrs[.foregroundColor] = NSColor.white
                numberAttrs[.backgroundColor] = NSColor.controlAccentColor
                textAttrs[.foregroundColor] = NSColor.white
                textAttrs[.backgroundColor] = NSColor.controlAccentColor
            }
            out.append(NSAttributedString(string: " \(i + 1)  ", attributes: numberAttrs))
            out.append(NSAttributedString(string: candidate + " ", attributes: textAttrs))
            if i < candidates.count - 1 {
                out.append(NSAttributedString(string: "\n", attributes: textAttrs))
            }
        }
        return out
    }
}
