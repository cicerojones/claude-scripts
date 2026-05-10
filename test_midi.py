import mido

print("Available MIDI output")
for name in mido.get_output_names():
    print(" ", name)
