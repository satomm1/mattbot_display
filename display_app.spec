# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

block_cipher = None

# Get the absolute path to the audio directory
home_dir = str(Path.home())
audio_dir = os.path.join(home_dir, 'Desktop', 'audio')

a = Analysis(['display_app.py'],
             pathex=['/home/jetson/mattbot_display'],
             binaries=[],
             datas=[(audio_dir, 'audio')],  # Use the absolute path here
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='display_app',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True )