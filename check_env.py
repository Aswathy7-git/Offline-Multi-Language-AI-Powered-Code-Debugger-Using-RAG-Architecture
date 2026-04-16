import shutil
import os

print(f"gcc: {shutil.which('gcc')}")
print(f"cc: {shutil.which('cc')}")
print(f"PATH: {os.environ.get('PATH')}")
