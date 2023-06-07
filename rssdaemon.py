import rssmaker
from subprocess import run
import time

while True:
    if rssmaker.execute():
        run(['git', 'add', 'dekudeals.xml'])
        run(['git', 'commit', '-m', 'RSS Content Updates'])
        run(['git', 'push'])
    time.sleep(60 * 5)
