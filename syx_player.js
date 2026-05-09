// syx_player.js — Max/MSP JS object for sequencing .syx files to the Minilogue
//
// Inlets:
//   0 — bang: send the current file and advance
//
// Outlets:
//   0 — raw MIDI bytes → connect to [midiout]
//   1 — status string  → connect to [message] or leave unconnected
//
// To set the directory at runtime, send the message:
//   setdir /path/to/your/syx/files
// (this overrides the hardcoded SYX_DIR below)

inlets  = 1;
outlets = 2;

var SYX_DIR = "/Users/stephenstrauss/syx";  // ← edit this path

var syx_files   = [];
var current_idx = 0;

// ---------------------------------------------------------------------------
// Initialise on load
// ---------------------------------------------------------------------------

function loadbang() {
    load_directory(SYX_DIR);
}

// ---------------------------------------------------------------------------
// Runtime directory override
// ---------------------------------------------------------------------------

function setdir() {
    // Collect all arguments into a path string (handles spaces)
    var path = arrayfromargs(arguments).join(" ");
    load_directory(path);
}

// ---------------------------------------------------------------------------
// Bang — send current file, advance index
// ---------------------------------------------------------------------------

function bang() {
    if (syx_files.length === 0) {
        post("syx_player: no files loaded — send 'setdir <path>' or check SYX_DIR\n");
        return;
    }

    var path = syx_files[current_idx];
    send_syx(path);

    var display = (current_idx + 1) + "/" + syx_files.length
                + "  " + filename_from_path(path);
    post("syx_player: " + display + "\n");
    outlet(1, display);

    current_idx = (current_idx + 1) % syx_files.length;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function load_directory(dir) {
    syx_files   = [];
    current_idx = 0;

    // Normalise: strip trailing slash so path joins are consistent
    dir = dir.replace(/\/$/, "");

    var folder = new Folder(dir);
    if (!folder) {
        post("syx_player: could not open directory: " + dir + "\n");
        return;
    }

    while (!folder.end) {
        if (folder.filename.match(/\.syx$/i)) {
            // folder.pathname is the directory path; append filename explicitly
            syx_files.push(dir + "/" + folder.filename);
        }
        folder.next();
    }
    folder.close();

    // Sort so playback order matches the filesystem name order
    syx_files.sort();

    post("syx_player: loaded " + syx_files.length
         + " .syx file(s) from " + dir + "\n");
}

// ---------------------------------------------------------------------------
// Diagnostics — send the message "listfiles" or "testsyx" to the js object
// ---------------------------------------------------------------------------

// Post all discovered paths to the console
function listfiles() {
    if (syx_files.length === 0) {
        post("syx_player: no files loaded\n");
        return;
    }
    post("syx_player: " + syx_files.length + " file(s):\n");
    for (var i = 0; i < syx_files.length; i++) {
        post("  [" + i + "] " + syx_files[i] + "\n");
    }
}

// Attempt to open the first file and report its size — confirms file access
function testsyx() {
    if (syx_files.length === 0) {
        post("syx_player: no files loaded\n");
        return;
    }
    var path = syx_files[0];
    var f = new File(path, "read", "ubin");
    if (!f.isopen) {
        post("syx_player: FAIL — could not open: " + path + "\n");
        return;
    }
    var size = f.eof;
    f.close();
    post("syx_player: OK — opened '" + filename_from_path(path)
         + "', size = " + size + " bytes"
         + (size === 408 ? " (correct)\n" : " (unexpected — expected 408)\n"));
}

// Step-by-step File access probe — run this before anything else if testsyx fails.
// Send the message "probe" to the js object.
function probe() {
    post("--- File access probe ---\n");

    // 1. Can File open the JS file itself by name alone (no path)?
    //    This always succeeds if Max's JS engine is working at all.
    var self = new File("syx_player.js", "read", "text");
    if (self.isopen) {
        post("  [1] OK  — opened syx_player.js by name (Max search path works)\n");
        self.close();
    } else {
        post("  [1] FAIL — could not open syx_player.js by name\n");
    }

    // 2. Can File open the first syx file by its full absolute path?
    if (syx_files.length > 0) {
        var fullpath = syx_files[0];
        var f2 = new File(fullpath, "read", "ubin");
        if (f2.isopen) {
            post("  [2] OK  — opened by absolute path: " + fullpath + "\n");
            f2.close();
        } else {
            post("  [2] FAIL — absolute path rejected: " + fullpath + "\n");
        }

        // 3. Can File open by filename alone (requires dir in Max search path)?
        var name = filename_from_path(fullpath);
        var f3 = new File(name, "read", "ubin");
        if (f3.isopen) {
            post("  [3] OK  — opened by filename only: " + name + "\n");
            post("           (add the syx folder to Max search path and use this form)\n");
            f3.close();
        } else {
            post("  [3] FAIL — filename-only also rejected: " + name + "\n");
            post("           If [1] passed but [2] and [3] both fail,\n");
            post("           this is a macOS sandbox/permissions issue.\n");
            post("           Fix: Options > File Preferences > add the syx folder,\n");
            post("           or move the syx files into the patch's own folder.\n");
        }
    } else {
        post("  [2,3] skipped — no files loaded yet\n");
    }

    post("--- end probe ---\n");
}

function send_syx(path) {
    var f = new File(path, "read", "ubin");
    if (!f.isopen) {
        post("syx_player: could not open file: " + path + "\n");
        return;
    }

    var size  = f.eof;
    var bytes = f.readbytes(size);
    f.close();

    outlet(0, bytes);
}

function filename_from_path(path) {
    var parts = path.split("/");
    return parts[parts.length - 1];
}
