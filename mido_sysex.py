import mido, os, time

SYX_DIR = "/Users/oi/repos/claudeProjects/output/"
PORT_NAME = "minilogue SOUND"

INTERVAL = 90.0

files = sorted(f for f in os.listdir(SYX_DIR) if f.endswith(".syx"))

with mido.open_output(PORT_NAME) as port:
    for i, name in enumerate(files):
        data = open(os.path.join(SYX_DIR, name), "rb").read()
        port.send(mido.Message("sysex", data=data[1:-1]))
        print(F"{i+1}/{len(files)} {name}")
        time.sleep(INTERVAL)

