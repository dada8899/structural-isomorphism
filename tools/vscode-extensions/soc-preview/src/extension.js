// SOC Preview — skeleton extension.
// On opening a CSV whose filename starts with `soc:`, parse the first numeric
// column and shell out to a small Python helper that prints "verdict alpha".
// The verdict is rendered in the VS Code status bar.
//
// This is a SKELETON — wiring is real but the Python helper script is
// intentionally minimal. Package as .vsix with `vsce package` if desired.

const vscode = require('vscode');
const path = require('path');
const cp = require('child_process');
const fs = require('fs');

let statusItem;

function activate(context) {
    statusItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right, 100
    );
    statusItem.text = 'SOC: idle';
    statusItem.show();
    context.subscriptions.push(statusItem);

    const disp = vscode.workspace.onDidOpenTextDocument(maybeFit);
    context.subscriptions.push(disp);

    const cmd = vscode.commands.registerCommand('socPreview.fit', () => {
        if (vscode.window.activeTextEditor) {
            maybeFit(vscode.window.activeTextEditor.document, /*force=*/ true);
        }
    });
    context.subscriptions.push(cmd);
}

function maybeFit(doc, force) {
    if (!doc || doc.languageId !== 'csv') return;
    const base = path.basename(doc.fileName);
    if (!force && !base.startsWith('soc:')) return;
    runSocFit(doc.fileName).then(({ verdict, alpha }) => {
        statusItem.text = `SOC: ${verdict} α=${alpha.toFixed(2)}`;
        statusItem.tooltip = `${doc.fileName}\nverdict: ${verdict}\nalpha:  ${alpha}`;
    }).catch((err) => {
        statusItem.text = `SOC: ERROR`;
        statusItem.tooltip = String(err);
    });
}

function runSocFit(csvPath) {
    return new Promise((resolve, reject) => {
        if (!fs.existsSync(csvPath)) return reject(new Error('file missing'));
        const helper = path.join(__dirname, 'fit_helper.py');
        cp.execFile('python3', [helper, csvPath], { timeout: 30000 },
            (err, stdout, stderr) => {
                if (err) return reject(new Error(stderr || err.message));
                try {
                    const out = JSON.parse(stdout.trim());
                    resolve(out);
                } catch (e) {
                    reject(new Error(`bad JSON: ${stdout}`));
                }
            }
        );
    });
}

function deactivate() {
    if (statusItem) statusItem.dispose();
}

module.exports = { activate, deactivate };
