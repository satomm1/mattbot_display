# mattbot_display

This repo provides the code for connecting the mobile robot to the touch screen display device. You can run the display script via:
```
python3 display_app.py
```
This will print messages sent to localhost:65432 to the screen. You may need to adjust the line `os.environ['AUDIODEV'] = 'plughw:<card number>,<device number>'` for your specific device/card number for the sound to work. I recommend adjusting the card number between 0 and 2.

To create the executable, run:
```
pyinstaller display_app.spec
```
The executable will be located at `/dist/display_app`. Copy the executable to the Desktop.

The expected file structure for audio is `~/Desktop/audio/`. You should move `default.mp3` to this directory.

To use the speakers, you will need to install some python packages/dependencies:
```
sudo apt update
pip3 install pygame
pip3 install pyinstaller
...

```