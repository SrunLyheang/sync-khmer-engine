import Cocoa
import InputMethodKit

// Entry point of the input method. macOS launches this app in the background the first
// time Sing Khmer is selected as the input source; it then stays running and receives
// key presses through InputMethodKit, which creates one SingKhmerInputController per
// text field being typed into (the class is named in Info.plist).

// Referenced so the controller class is certain to be linked into the binary.
_ = SingKhmerInputController.self

let connectionName = Bundle.main.infoDictionary?["InputMethodConnectionName"] as? String
    ?? "SingKhmer_1_Connection"

guard let server = IMKServer(name: connectionName, bundleIdentifier: Bundle.main.bundleIdentifier) else {
    NSLog("SingKhmer: could not start the input method server (\(connectionName))")
    exit(1)
}

if Shared.store.engine == nil {
    NSLog("SingKhmer: running without a dictionary; keys will pass through unchanged")
}

NSApplication.shared.run()
