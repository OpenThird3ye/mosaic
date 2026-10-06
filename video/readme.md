# 4K 30fps Video Test 
4K 30fps Video Test Signal Generator — with live display window\
No OpenCV required. Uses: pillow, numpy, imageio-ffmpeg, tkinter (built-in)

Install:
    pip install pillow numpy imageio-ffmpeg

Usage:
    python generate_test_signal.py                  # display only
    python generate_test_signal.py --save           # display + save MP4
    python generate_test_signal.py --save --crf 18 --duration 30
    python generate_test_signal.py --no-display --save  # headless encode only

Press  Q  or close the window to quit.
