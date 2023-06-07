import rssmaker
from subprocess import run
import time

git = r'C:\Program Files\Git\bin\git.exe'

while True:
    if rssmaker.execute():
        run([git, 'add', 'dekudeals.xml'])
        run([git, 'commit', '-m', 'RSS Content Updates'])
        run([git, 'push'])
    time.sleep(60 * 5)
