# mattbot_display

This repo provides the code for connecting the mobile robot to the touch screen display device. You can run the display script via:
```
python3 display_app.py
```
This will print messages sent to localhost:65432 to the screen.

To create the executable, run:
```
pyinstaller --onefile display_app.py
```
The executable will be located at `/dist/display_app`.

To use the speakers, you will need to install some python packages/dependencies:
```
sudo apt update
...

```