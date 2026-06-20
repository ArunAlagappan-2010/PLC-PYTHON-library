import * as vscode from "vscode";
import * as cp from "child_process";
import * as os from "os";
import * as path from "path";
import * as fs from "fs";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

function startLanguageServer(): void {
  const exec = {
    command: cliCommand(),
    args: ["lsp"],
    transport: TransportKind.stdio,
  };
  const serverOptions: ServerOptions = { run: exec, debug: exec };
  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "st" },
      { scheme: "file", language: "il" },
      { scheme: "file", language: "ld" },
      { scheme: "file", language: "fbd" },
      { scheme: "file", language: "sfc" },
    ],
  };
  client = new LanguageClient("plcpy", "plcpy Language Server", serverOptions, clientOptions);
  client.start();
}

const EXT_LANG: Record<string, string> = {
  ".st": "st", ".il": "il", ".ld": "ld",
  ".fbd": "fbd", ".sfc": "sfc", ".py": "python",
};

const ALL_TARGETS = ["python", "st", "il", "ld", "fbd", "sfc", "scl", "l5x"];

function cliCommand(): string {
  return vscode.workspace.getConfiguration("plcpy").get<string>("command", "plcpy");
}

function langForDocument(doc: vscode.TextDocument): string | undefined {
  if (EXT_LANG[path.extname(doc.fileName).toLowerCase()]) {
    return EXT_LANG[path.extname(doc.fileName).toLowerCase()];
  }
  // fall back to the editor's language id if it is one we recognise
  if (["st", "il", "ld", "fbd", "sfc", "python"].includes(doc.languageId)) {
    return doc.languageId;
  }
  return undefined;
}

/** Write the document text to a temp file with the right extension and run a
 *  plcpy subcommand. Returns stdout (for convert) or "" (for visualize). */
function runPlcpy(args: string[], onDone: (err: string | null, stdout: string) => void): void {
  cp.execFile(cliCommand(), args, { maxBuffer: 16 * 1024 * 1024 }, (err, stdout, stderr) => {
    if (err) {
      onDone(stderr || err.message, "");
    } else {
      onDone(null, stdout);
    }
  });
}

function writeTemp(content: string, ext: string): string {
  const file = path.join(os.tmpdir(), `plcpy-${Date.now()}${ext}`);
  fs.writeFileSync(file, content, "utf-8");
  return file;
}

function visualize(context: vscode.ExtensionContext): void {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showErrorMessage("plcpy: open a PLC or Python file first.");
    return;
  }
  const doc = editor.document;
  const fromLang = langForDocument(doc);
  if (!fromLang) {
    vscode.window.showErrorMessage("plcpy: unrecognised file type (.st/.il/.ld/.fbd/.sfc/.py).");
    return;
  }
  const toLang = vscode.workspace.getConfiguration("plcpy").get<string>("defaultTarget", "python");
  const srcExt = path.extname(doc.fileName) || ".txt";

  const panel = vscode.window.createWebviewPanel(
    "plcpyVisualize",
    `plcpy: ${fromLang} ↔ ${toLang}`,
    vscode.ViewColumn.Beside,
    { enableScripts: false }
  );

  const refresh = () => {
    const srcFile = writeTemp(doc.getText(), srcExt);
    const outFile = writeTemp("", ".html");
    runPlcpy(
      ["visualize", "--from", fromLang, "--to", toLang, srcFile, "-o", outFile],
      (err) => {
        if (err) {
          panel.webview.html = `<body style="font-family:sans-serif;padding:16px">
            <h3>plcpy error</h3><pre>${escapeHtml(err)}</pre></body>`;
          return;
        }
        panel.webview.html = fs.readFileSync(outFile, "utf-8");
        try { fs.unlinkSync(srcFile); fs.unlinkSync(outFile); } catch { /* ignore */ }
      }
    );
  };

  refresh();
  // synchronized: re-render whenever this document is saved
  const sub = vscode.workspace.onDidSaveTextDocument((saved) => {
    if (saved.uri.toString() === doc.uri.toString()) {
      refresh();
    }
  });
  panel.onDidDispose(() => sub.dispose(), null, context.subscriptions);
}

async function convert(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showErrorMessage("plcpy: open a file first.");
    return;
  }
  const doc = editor.document;
  const fromLang = langForDocument(doc);
  if (!fromLang) {
    vscode.window.showErrorMessage("plcpy: unrecognised file type.");
    return;
  }
  const toLang = await vscode.window.showQuickPick(
    ALL_TARGETS.filter((t) => t !== fromLang),
    { placeHolder: "Convert to..." }
  );
  if (!toLang) {
    return;
  }
  const srcFile = writeTemp(doc.getText(), path.extname(doc.fileName) || ".txt");
  runPlcpy(["convert", "--from", fromLang, "--to", toLang, srcFile], async (err, stdout) => {
    try { fs.unlinkSync(srcFile); } catch { /* ignore */ }
    if (err) {
      vscode.window.showErrorMessage(`plcpy: ${err}`);
      return;
    }
    const out = await vscode.workspace.openTextDocument({
      content: stdout,
      language: toLang === "python" ? "python" : toLang,
    });
    vscode.window.showTextDocument(out, vscode.ViewColumn.Beside);
  });
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string));
}

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("plcpy.visualize", () => visualize(context)),
    vscode.commands.registerCommand("plcpy.convert", () => convert())
  );
  try {
    startLanguageServer();
  } catch (e) {
    // LSP is optional — convert/visualize still work without it
    console.error("plcpy: failed to start language server", e);
  }
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}
