import pyvisa
import numpy as np
import sys
import csv
import time

# Removes the data header (#9XXXXXXXXX)
def remove_header(data):
    return data[11:].strip()

### Connect to the oscilloscope
rm = pyvisa.ResourceManager()
resources = rm.list_resources()
if not resources:
    print("Could not find a scope!")
    exit(-1)

# Assume that the first thing in the list is the scope
# Not the best thing to do, but okay for now
scope = rm.open_resource(resources[0])

# Try to query the scope ID to make sure we are connected
idn = scope.query("*IDN?")
if not idn:
    print("Could not query IDN, check scope connection!")
    exit(-1)

print(f"Connected to {idn}.")

print("Setting up scope...")
scope.write(':CHAN1:DISP ON')  # Turn on Channel 1
scope.write(':CHAN2:DISP ON')  # Turn on Channel 2

scope.write(':CHAN1:SCAL 2')   # 2V scale on Channel 1
scope.write(':CHAN2:SCAL 2')   # 2V scale on Channel 2

# Set trigger mode to normal, and trigger on channel 1
scope.write(':TRIG:SWE NORM')        # Normal sweep
scope.write(':TRIG:MODE EDGE')       # Edge trigger
scope.write(':TRIG:EDG:SOUR CHAN1')  # Channel 1

# Trigger at 500 mV
scope.write(':TRIG:EDG:LEV 0.5')

# Set timebase to 200 us/div
scope.write(':TIM:DEL:SCAL 0.0002')

# Normal acq mode, averages a bit weird to work with
scope.write(':ACQ:TYPE NORM')

plaintext = 35


# Loop for data collection
while (plaintext <= 255):
    csv_filename = 'csv/trustbust_data_' + str(plaintext) + ".csv"
    file = open(csv_filename, mode='w', newline='')
    writer = csv.writer(file)
    print(f"Begin capture for text: {plaintext}.")

    sample = 0
    sample_data = []
    while (sample < 10):
        print("Waiting for trigger...")
        # Stop the scope, set to single mode
        scope.write(':SING')
        # Wait for trigger
        rdy = ""
        # No clue why the status has a newline attached
        while (rdy != "STOP\n"):
            rdy = scope.query(':TRIG:STAT?')  # I hate Python so much

        # Query the waveform data from channel 2
        scope.write(':WAV:SOUR CHAN2')
        scope.write(':WAV:MODE NORM') # Normal mode
        scope.write(':WAV:FORM ASC')  # ASCII format

        # Get the data
        waveform_data = scope.query(':WAV:DATA?')
        # Remove the header
        waveform_data = remove_header(waveform_data)

        # Also get channel 1 to remove irrelevant points
        scope.write(':WAV:SOUR CHAN1')
        chan1_data = scope.query(":WAV:DATA?")
        chan1_data = remove_header(chan1_data)

        # Process the waveform data
        #print(waveform_data)
        # Move data to numpy arrays
        waveform_values = np.fromstring(waveform_data, sep=',', dtype=np.float64)
        trigger_values  = np.fromstring(chan1_data, sep=',', dtype=np.float64)
        #with np.printoptions(threshold=sys.maxsize):
        #    print(trigger_values)
        #print(waveform_values)

        # Fail-safe if for some reason we capture an empty screen
        if trigger_values.size == 0 or waveform_values.size == 0:
            print("Did not capture anything, retrying...")
            scope.write(":RUN")  # Resume scope, as we were stopped before
            continue

        # Mask off values where encryption is not active
        mask = trigger_values >= 2.0
        waveform_values = trigger_values[mask]
        #print(waveform_values)
        if (waveform_values.size < 700):
            print("Drift detected, retrying...")
            continue
        sample_data.append(waveform_values)

        print(f"Captured data at {time.time()}")

        # Resume scope
        scope.write(':RUN')
        sample += 1

    # Get the average
    # Pad the arrays, since sometimes encryption takes shorter or longer
    # This may be important, we should make note of this
    max_len = max(len(a) for a in sample_data)
    padded = np.array([np.pad(a, (0, max_len - len(a)), mode='constant') for a in sample_data])
    average = np.mean(padded, axis=0, dtype=np.float64)
    
    # Write the data
    for point in average:
        writer.writerow(np.array([point]))

    plaintext += 1
    file.close()
    input("Press user button on the board to change plaintext, then Enter to continue...")

# Close the connection
scope.close()

