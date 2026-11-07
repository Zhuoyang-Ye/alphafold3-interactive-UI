import Cocoa
import WebKit

@main
class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var serverProcess: Process?
    let targetURL = URL(string: "http://127.0.0.1:8765")!
    var checkTimer: Timer?
    var retriesLeft = 20

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupMenu()
        setupWindow()
        startServerIfNeeded()
    }

    func setupWindow() {
        let screenSize = NSScreen.main?.visibleFrame.size ?? CGSize(width: 1400, height: 900)
        let width = min(1360, screenSize.width * 0.9)
        let height = min(920, screenSize.height * 0.9)
        let rect = NSRect(x: (screenSize.width - width) / 2, y: (screenSize.height - height) / 2, width: width, height: height)

        window = NSWindow(
            contentRect: rect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "AlphaFold 3 · Interaction Studio"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .visible
        window.minSize = NSSize(width: 960, height: 680)
        window.isReleasedWhenClosed = false

        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")
        let prefs = WKWebpagePreferences()
        prefs.allowsContentJavaScript = true
        config.defaultWebpagePreferences = prefs

        webView = WKWebView(frame: rect, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.autoresizingMask = [.width, .height]

        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        loadInitialPage()
    }

    func loadInitialPage() {
        showLoadingScreen()
        pingServer { [weak self] isRunning in
            DispatchQueue.main.async {
                if isRunning {
                    self?.webView.load(URLRequest(url: self!.targetURL))
                } else {
                    self?.waitForServer()
                }
            }
        }
    }

    func showLoadingScreen() {
        let html = """
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {
              margin: 0;
              background: #0d1513;
              color: #ecf4f0;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
              display: flex;
              align-items: center;
              justify-content: center;
              height: 100vh;
              text-align: center;
            }
            .card {
              max-width: 480px;
              padding: 40px;
              background: #14201c;
              border: 1px solid #243831;
              border-radius: 16px;
              box-shadow: 0 20px 50px rgba(0,0,0,0.5);
            }
            .logo { font-size: 56px; color: #b8f07a; margin-bottom: 12px; }
            h2 { margin: 0 0 10px; font-size: 22px; font-weight: 600; }
            p { font-size: 14px; color: #8d9e96; line-height: 1.6; margin: 0 0 24px; }
            .spinner {
              width: 32px; height: 32px; border: 3px solid #243831;
              border-top-color: #2bb386; border-radius: 50%;
              animation: spin 1s linear infinite; margin: 0 auto 16px;
            }
            @keyframes spin { to { transform: rotate(360deg); } }
            .btn {
              display: inline-block; padding: 10px 18px; font-size: 13px; font-weight: 600;
              background: #2bb386; color: #fff; border: 0; border-radius: 8px; cursor: pointer;
              text-decoration: none;
            }
            .btn:hover { background: #37c897; }
          </style>
        </head>
        <body>
          <div class="card">
            <div class="logo">⌬</div>
            <h2>AlphaFold 3 Explorer</h2>
            <div class="spinner"></div>
            <p>Connecting to local AlphaFold 3 environment…<br>Starting local studio backend at 127.0.0.1:8765</p>
            <button class="btn" onclick="location.reload()">Retry Connection</button>
          </div>
        </body>
        </html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    func pingServer(completion: @escaping (Bool) -> Void) {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8765/api/status")!)
        request.timeoutInterval = 1.0
        let task = URLSession.shared.dataTask(with: request) { _, response, error in
            if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                completion(true)
            } else {
                completion(false)
            }
        }
        task.resume()
    }

    func startServerIfNeeded() {
        pingServer { [weak self] isRunning in
            if !isRunning {
                self?.launchServerScript()
            }
        }
    }

    func launchServerScript() {
        let fileManager = FileManager.default
        let currentDir = Bundle.main.bundlePath
        let possibleRoots = [
            (currentDir as NSString).deletingLastPathComponent,
            ((currentDir as NSString).deletingLastPathComponent as NSString).deletingLastPathComponent,
            NSHomeDirectory() + "/alphafold3",
            fileManager.currentDirectoryPath
        ]

        var scriptPath: String?
        for root in possibleRoots {
            let candidate = root + "/run_explorer.sh"
            if fileManager.fileExists(atPath: candidate) {
                scriptPath = candidate
                break
            }
        }

        guard let script = scriptPath else { return }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/bin/bash")
        proc.arguments = [script]
        proc.currentDirectoryURL = URL(fileURLWithPath: (script as NSString).deletingLastPathComponent)
        try? proc.run()
        self.serverProcess = proc
    }

    func waitForServer() {
        checkTimer?.invalidate()
        retriesLeft = 30
        checkTimer = Timer.scheduledTimer(withTimeInterval: 0.8, repeats: true) { [weak self] timer in
            guard let self = self else { return }
            self.pingServer { isUp in
                DispatchQueue.main.async {
                    if isUp {
                        timer.invalidate()
                        self.webView.load(URLRequest(url: self.targetURL))
                    } else {
                        self.retriesLeft -= 1
                        if self.retriesLeft <= 0 {
                            timer.invalidate()
                        }
                    }
                }
            }
        }
    }

    func setupMenu() {
        let mainMenu = NSMenu()

        // App Menu
        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About AlphaFold 3 Explorer", action: #selector(openAbout), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Local Data Portal…", action: #selector(openPortal), keyEquivalent: "d")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Hide AlphaFold 3 Explorer", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let hideOthers = NSMenuItem(title: "Hide Others", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        hideOthers.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(hideOthers)
        appMenu.addItem(withTitle: "Show All", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Quit AlphaFold 3 Explorer", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        // File Menu
        let fileMenuItem = NSMenuItem()
        let fileMenu = NSMenu(title: "File")
        fileMenu.addItem(withTitle: "New Experiment…", action: #selector(newExperiment), keyEquivalent: "n")
        fileMenu.addItem(withTitle: "Import Structure…", action: #selector(importStructure), keyEquivalent: "o")
        fileMenu.addItem(NSMenuItem.separator())
        fileMenu.addItem(withTitle: "Local Data Portal…", action: #selector(openPortal), keyEquivalent: "p")
        fileMenu.addItem(withTitle: "Close Window", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        fileMenuItem.submenu = fileMenu
        mainMenu.addItem(fileMenuItem)

        // View Menu
        let viewMenuItem = NSMenuItem()
        let viewMenu = NSMenu(title: "View")
        viewMenu.addItem(withTitle: "Toggle Theme (Dark / Light)", action: #selector(toggleTheme), keyEquivalent: "t")
        viewMenu.addItem(withTitle: "Toggle Explorer / Scientist Mode", action: #selector(toggleMode), keyEquivalent: "e")
        viewMenu.addItem(NSMenuItem.separator())
        viewMenu.addItem(withTitle: "Reload", action: #selector(reloadWebView), keyEquivalent: "r")
        viewMenu.addItem(withTitle: "Reset 3D View", action: #selector(reset3DView), keyEquivalent: "0")
        viewMenu.addItem(NSMenuItem.separator())
        viewMenu.addItem(withTitle: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        viewMenuItem.submenu = viewMenu
        mainMenu.addItem(viewMenuItem)

        // Help Menu
        let helpMenuItem = NSMenuItem()
        let helpMenu = NSMenu(title: "Help")
        helpMenu.addItem(withTitle: "AlphaFold 3 Quick Guide", action: #selector(openGuide), keyEquivalent: "/")
        helpMenu.addItem(withTitle: "Open Online Demo", action: #selector(openOnlineDemo), keyEquivalent: "")
        helpMenu.addItem(withTitle: "Source on GitHub", action: #selector(openGitHub), keyEquivalent: "")
        helpMenuItem.submenu = helpMenu
        mainMenu.addItem(helpMenuItem)

        NSApp.mainMenu = mainMenu
    }

    @objc func reloadWebView() { webView.reload() }
    @objc func toggleTheme() { webView.evaluateJavaScript("window.toggleAppTheme && window.toggleAppTheme()", completionHandler: nil) }
    @objc func toggleMode() { webView.evaluateJavaScript("window.toggleAppMode && window.toggleAppMode()", completionHandler: nil) }
    @objc func newExperiment() { webView.evaluateJavaScript("document.getElementById('new-experiment')?.click()", completionHandler: nil) }
    @objc func importStructure() { webView.evaluateJavaScript("document.getElementById('import-open')?.click()", completionHandler: nil) }
    @objc func openPortal() { webView.evaluateJavaScript("window.openLocalPortal && window.openLocalPortal()", completionHandler: nil) }
    @objc func openGuide() { webView.evaluateJavaScript("window.openQuickGuide && window.openQuickGuide()", completionHandler: nil) }
    @objc func reset3DView() { webView.evaluateJavaScript("document.getElementById('reset-view')?.click()", completionHandler: nil) }
    @objc func openOnlineDemo() {
        if let url = URL(string: "https://zhuoyang-ye.github.io/alphafold3-interactive-UI/") {
            NSWorkspace.shared.open(url)
        }
    }
    @objc func openGitHub() {
        if let url = URL(string: "https://github.com/Zhuoyang-Ye/alphafold3") {
            NSWorkspace.shared.open(url)
        }
    }
    @objc func openAbout() {
        let alert = NSAlert()
        alert.messageText = "AlphaFold 3 · Interaction Studio"
        alert.informativeText = "Version 2.0 (macOS Desktop Edition)\n\nInteractive 3D molecular structure explorer powered by local AlphaFold 3 and 3Dmol.js.\nYour molecules. Your machine."
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }

    func applicationWillTerminate(_ notification: Notification) {
        serverProcess?.terminate()
    }
}
