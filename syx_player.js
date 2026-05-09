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

    var folder = new Folder(dir);
    if (!folder) {
        post("syx_player: could not open directory: " + dir + "\n");
        return;
    }

    while (!folder.end) {
        if (folder.filename.match(/\.syx$/i)) {
            syx_files.push(folder.pathname);
        }
        folder.next();
    }
    folder.close();

    // Sort so playback order matches the filesystem name order
    syx_files.sort();

    post("syx_player: loaded " + syx_files.length
         + " .syx file(s) from " + dir + "\n");
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
