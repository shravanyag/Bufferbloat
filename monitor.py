from time import sleep, time
from subprocess import *
import re

default_dir = '.'

def monitor_qlen(iface, interval_sec, fname):
    pat_queued = re.compile(r'backlog\s[^\s]+\s([\d]+)p')
    #print(pat_queued)
    cmd = "tc -s qdisc show dev %s" % (iface)
    #print(cmd)
    ret = []
    open(fname, 'w').write('')
    while 1:
        p = Popen(cmd, shell=True, stdout=PIPE)
        output = p.stdout.read()
        print("output = ", output)
        # Not quite right, but will do for now
        matches = pat_queued.findall(str(output))
        #print("matches = ", matches)
        if matches:
            ret.append(matches[0])
            t = "%f" % time()
            open(fname, 'a').write(t + ',' + matches[0] + '\n')
        sleep(interval_sec)
    #open('./output/q.txt', 'w').write('\n'.join(ret))
    return

def monitor_devs_ng(fname="%s/txrate.txt" % default_dir, interval_sec=0.01):
    """Uses bwm-ng tool to collect iface tx rate stats.  Very reliable."""
    cmd = ("sleep 1; bwm-ng -t %s -o csv "
           "-u bits -T rate -C ',' > %s" %
           (interval_sec * 1000, fname))
    Popen(cmd, shell=True).wait()
