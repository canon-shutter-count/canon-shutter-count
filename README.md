# canon-shutter-count

Read the shutter count from a Canon EOS R-series camera over USB. It's free, has no app, needs no driver swap, and doesn't touch the camera's firmware.

```
> python shutter_count.py
Camera:   Canon EOS R8 (firmware 1.6.0)
Mechanical shutter: about 63,000
Total releases:     about 83,000  (includes electronic shutter)
Electronic:         about 20,000
Values are in steps of 1,000. ...
Raw 0xD167: [16, 1, 63000, 83000]
```

## Quick start (Windows)

1. Get the camera ready for USB (see **Camera setup** below), then connect it and switch it on.
2. On this page, click the green **Code** button, then **Download ZIP**, and extract it.
3. Double-click **`run.bat`**.

The first run sets up a private Python environment inside that folder. Nothing is installed system-wide. You need Python 3.10 or newer; if it's missing, `run.bat` tells you how to get it. `run.bat` is a short text file, so open it in Notepad to see exactly what it does. Windows may ask whether to run a downloaded file. That's normal.

If you already use Python: `pip install comtypes`, then `python shutter_count.py`.

### Camera setup

The camera has to show up as a camera to the PC. If the script says "No Canon camera found", check these:

- **USB connection setting.** If the camera is set up for a phone, Windows sees only an "iAP Interface" with no driver, and the script can't reach the camera. Change the setting and reconnect. A leftover "iAP Interface" with an error next to a working camera entry is harmless.
  - **EOS R8:** Setup menu (wrench icon), page 4, **Choose USB connection app**. Pick **Photo Import/Remote Control**. The other two choices, **Video calls/streaming** and **Canon app(s) for iPhone**, hide the camera from the script.
  - **EOS R:** Setup menu (wrench icon), page 5, **Wireless communication settings**:
    - **Wi-Fi settings** → set **Wi-Fi** to **Disable**. **Wi-Fi function** then greys out.
    - **Bluetooth function** → set **Bluetooth function** to **Disable**.
  - Other bodies: look in the Setup menu for a USB connection setting or wireless communication settings.
- **Camera switched on, not asleep.** If auto power off kicks in, switch the camera off and on again.
- **Use a data cable.** Some USB-C cables only charge.
- **Close Canon EOS Utility** and any other app using the camera. Only one program can talk to it at a time.
- A memory card is optional. The count is stored in the camera, not on the card.

When it's connected, the R8's screen shows the battery level and a laptop symbol. The EOS R just keeps its normal display and gives no sign of USB mode. On either camera, it should also appear in File Explorer under This PC, and in Device Manager under Portable Devices with its model name.

It uses Windows' own camera driver, the same one that lets File Explorer see the camera. You don't need Zadig, libusb or any extra driver.

## Tested cameras

| Camera | Firmware | Result |
|---|---|---|
| EOS R | 1.8.0 | Works. Mechanical and total both report. |
| EOS R8 | 1.6.0 | Works. Mechanical and total report separately. |

Have another body, such as an R5, R6, RP, R7, R10 or R50? Please run it and open an issue with the output. Delete the `Raw` line first if you'd rather not share it, though it holds nothing personal.

## How it works

Canon cameras speak PTP over USB, with Canon's own extensions. After the script puts the camera in remote and event mode, the camera pushes a burst of property-change events. One of them is property **0xD167** (libgphoto2 calls it `ShutterReleaseCounter`), with the payload:

```
[16, 1, mechanical, total]
```

- **mechanical**: actuations of the mechanical shutter.
- **total**: all releases, including the fully electronic shutter.
- Both are in **steps of 1,000**, and both survive a power-cycle.

We confirmed it was a live counter by firing about 1,000 shots and watching the values step from 21000 to 22000 to 23000 on an EOS R. On an R8, fully electronic bursts moved only the total.

Opcodes sent (all read-only or mode switches): `0x1001` GetDeviceInfo, `0x9114` SetRemoteMode, `0x9115` SetEventMode, `0x913D` SetRequestOLCInfoGroup, `0x9116` GetEvent. The script refuses any other opcode.

## Caveats

- **Steps of 1,000.** We haven't checked whether the camera rounds up or down. Paid tools reportedly show the same 1,000-step precision, at least for the EOS R. We haven't checked that ourselves.
- **Lag.** Right after shooting, the mechanical value can trail the total for a few seconds. Run the script again.
- **Not verified against a paid app yet.** If you have a reading from one, please share it in an issue.
- **Don't send `0x9127` (RequestDevicePropValue) to these cameras.** It hung both our test bodies until they were power-cycled. This script never sends it.

## Other platforms

The protocol is plain USB PTP. On Linux or macOS, libgphoto2-based tools can probably reach 0xD167 too. A port or a PR is welcome.

## License

MIT. See [LICENSE](LICENSE). An independent open-source tool, not affiliated with Canon or any commercial shutter-count app.
