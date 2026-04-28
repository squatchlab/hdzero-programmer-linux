HDzero Programmer Tool - For MAC
Developed by - Gunther_FPV (Gunther Votteler)
Github - https://github.com/gvotteler
Version 2.0

#############################################
This tool provide a usefull way to update or flash your Hdzero VTX's.

#############################################
Pre-requieriments.

Before to use this tool YOU need follow the next steps.

1. Open your terminal app (CLI)

2. Install brew in your MAC, if you not have installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

3. Install flashrom
brew install flashrom

4. Run this commands in the same folder that you have the HDZeroProgrammerTool.app
xattr -dr com.apple.quarantine "HDZeroProgrammerTool.app"
codesign --deep --force --sign - "HDZeroProgrammerTool.app"

5. If you want, move the app to Applications folder or desire folder.

##########################################################################################
##################################FOR LOCAL LOAD##########################################


1. Download the Hdzero firmware that you want flash in your VTX (https://www.hd-zero.com/document) section VTX Firmware

2. Extract the zip file, locate the zip file of your vtx and extract too.

3. Open HDZeroProgrammerTool.app, browse the folder and choose the .bin file extracted.

4. Flash.

5. Optional (If you want, create a backup of the current firmware before to flash)


##########################################################################################
##########################################################################################


Licence - MIT
Copyright (c) 2025 Gunther Votteler
Instagram - @gunther_fpv
Youtube - https://www.youtube.com/@FPVecinos

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

USE UNDER YOUR OWN RISK

