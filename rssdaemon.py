import rssmaker
from subprocess import run
import time

git = r'C:\Program Files\Git\bin\git.exe'
sleep_in_minutes = 5

while True:
    if rssmaker.execute():
        run([git, 'add', 'dekudeals.xml'])
        run([git, 'commit', '-m', 'RSS Content Updates'])
        run([git, 'push'])
    print('Going to sleep for', sleep_in_minutes, 'minutes')
    time.sleep(sleep_in_minutes * 60)
