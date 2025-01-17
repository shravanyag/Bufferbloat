#!/usr/bin/python
"CS244 Spring 2015 Assignment 1: Bufferbloat"

from mininet.topo import Topo
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.log import lg, info
from mininet.util import dumpNodeConnections
from mininet.cli import CLI
from mininet.clean import cleanup

from subprocess import Popen, PIPE
from time import sleep, time
from multiprocessing import Process
from argparse import ArgumentParser
from helper import avg, stdev
from monitor import monitor_qlen
import termcolor as T

import sys
import os
import math

# TODO: Don't just read the TODO sections in this code.  Remember that
# one of the goals of this assignment is for you to learn how to use
# Mininet. :-)

parser = ArgumentParser(description="Queue buffer size tests")

parser.add_argument('--bw-net', '-b',
                    type=float,
                    help="Bandwidth of bottleneck (network) link (Mb/s)",
                    required=True)

parser.add_argument('--delay',
                    type=float,
                    help="Link propagation delay (ms)",
                    required=True)

parser.add_argument('--dir', '-d',
                    help="Directory to store outputs",
                    required=True)

parser.add_argument('--time', '-t',
                    help="Duration (sec) to run the experiment",
                    type=int,
                    default=10)

parser.add_argument('--maxq',
                    type=int,
                    help="Max buffer size of network interface in packets",
                    default=100)

# Linux uses CUBIC-TCP by default that doesn't have the usual sawtooth
# behaviour.  For those who are curious, invoke this script with
# --cong cubic and see what happens...
# sysctl -a | grep cong should list some interesting parameters.
parser.add_argument('--cong',
                    help="Congestion control algorithm to use",
                    default="reno")

# Expt parameters
args = parser.parse_args()

class MultiServerTopo(Topo):
    "Dumbell topology with 1 subnet representing the host and the other server."

    def build(self):
        hosts = []
        switches = []
        for i in range(1,5):
            hosts.append(self.addHost('h%d'%(i)))

        for i in range(1,5):
            hosts.append(self.addHost('s%d'%(i)))

        switch1 = self.addSwitch('r1')
        switch2 = self.addSwitch('r2')
        #observe r1-eth5

        for i in range(4):
            self.addLink(switch1, hosts[i], bw=args.bw_net, delay=args.delay,
                         max_queue_size=args.maxq)
            
        for i in range(4,8):
            self.addLink(switch2, hosts[i], bw=args.bw_net, delay=args.delay,
                         max_queue_size=args.maxq)
            
        self.addLink(switch1, switch2, bw=args.bw_net, delay=args.delay, 
                     max_queue_size=args.maxq)

# tcp_probe is a kernel module which records cwnd over time. In linux >= 4.16
# it has been replaced by the tcp:tcp_probe kernel tracepoint.

def start_tcpprobe(outfile="cwnd.txt"):
    os.system("rmmod tcp_probe; modprobe tcp_probe full=1;")
    Popen("cat /proc/net/tcpprobe > %s/%s" % (args.dir, outfile),
          shell=True)

def stop_tcpprobe():
    Popen("killall -9 cat", shell=True).wait()

def start_qmon(iface, interval_sec, outfile):
    monitor = Process(target=monitor_qlen,
                      args=(iface, interval_sec, outfile))
    monitor.start()
    return monitor

def start_iperf(net):
    s1 = net.get('s1')
    print ("Starting iperf server on s1...")
    s1.popen("iperf -s -w 16m")

    s2 = net.get('s2')
    print ("Starting iperf server on s2...")
    s2.popen("iperf -s -w 16m")

    s3 = net.get('s3')
    print ("Starting iperf server on s3...")
    s3.popen("iperf -s -w 16m")

    s4 = net.get('s4')
    print ("Starting iperf server on s4...")
    s4.popen("iperf -s -w 16m")
    # For those who are curious about the -w 16m parameter, it ensures
    # that the TCP flow is not receiver window limited.  If it is,
    # there is a chance that the router buffer may not get filled up.
    
    # TODO: Start the iperf client on h1.  Ensure that you create a
    # long lived TCP flow. You may need to redirect iperf's stdout to avoid blocking.
    h1 = net.get('h1')
    h1.popen("iperf -c %s -t %s > %s/iperf.out" % (s1.IP(), args.time, args.dir), shell=True)

    h2 = net.get('h2')
    h2.popen("iperf -c %s -t %s > %s/iperf.out" % (s2.IP(), args.time, args.dir), shell=True)

    h3 = net.get('h3')
    h3.popen("iperf -c %s -t %s > %s/iperf.out" % (s3.IP(), args.time, args.dir), shell=True)

    h4 = net.get('h4')
    h4.popen("iperf -c %s -t %s > %s/iperf.out" % (s4.IP(), args.time, args.dir), shell=True)

def start_webserver(net):
    s1 = net.get('s1')
    proc1 = s1.popen("python http/webserver.py", shell=True)

    s2 = net.get('s2')
    proc2 = s2.popen("python http/webserver.py", shell=True)

    s3 = net.get('s3')
    proc3 = s3.popen("python http/webserver.py", shell=True)

    s4 = net.get('s4')
    proc4 = s4.popen("python http/webserver.py", shell=True)
    sleep(1)
    return [proc1, proc2, proc3, proc4]

def start_ping(net):
    # TODO: Start a ping train from h1 to h2 (or h2 to h1, does it
    # matter?)  Measure RTTs every 0.1 second.  Read the ping man page
    # to see how to do this.

    # Hint: Use host.popen(cmd, shell=True).  If you pass shell=True
    # to popen, you can redirect cmd's output using shell syntax.
    # i.e. ping ... > /path/to/ping.txt
    # Note that if the command prints out a lot of text to stdout, it will block
    # until stdout is read. You can avoid this by runnning popen.communicate() or
    # redirecting stdout
    h1 = net.get('h1')
    s4 = net.get('s4')
    popen = h1.popen("ping -i 0.1 %s > %s/ping.txt"%(s4.IP(), args.dir), shell=True)

def bufferbloat():
    if not os.path.exists(args.dir):
        os.makedirs(args.dir)
    os.system("sysctl -w net.ipv4.tcp_congestion_control=%s" % args.cong)

    # Cleanup any leftovers from previous mininet runs
    cleanup()

    topo = MultiServerTopo()
    net = Mininet(topo=topo, link=TCLink) #, host=CPULimitedHost, link=TCLink
    net.start()
    # This dumps the topology and how nodes are interconnected through
    # links.
    dumpNodeConnections(net.hosts)
    # This performs a basic all pairs ping test.
    net.pingAll()

    # Start all the monitoring processes
    #start_tcpprobe("cwnd.txt")
    start_ping(net)

    # TODO: Start monitoring the queue sizes.  Since the switch I
    # created is "s0", I monitor one of the interfaces.  Which
    # interface?  The interface numbering starts with 1 and increases.
    # Depending on the order you add links to your network, this
    # number may be 1 or 2.  Ensure you use the correct number.
    #
    qmon1 = start_qmon(iface='r1-eth5', interval_sec=0.01,
                        outfile='%s/q-r1.txt' % (args.dir))
    
    qmon2 = start_qmon(iface='r2-eth5', interval_sec=0.01,
                        outfile='%s/q-r2.txt' % (args.dir))

    # TODO: Start iperf, webservers, etc.
    start_iperf(net)
    start_webserver(net)

    # Hint: The command below invokes a CLI which you can use to
    # debug.  It allows you to run arbitrary commands inside your
    # emulated hosts h1 and h2.
    #
    # CLI(net)

    # TODO: measure the time it takes to complete webpage transfer
    # from h1 to h2 (say) 3 times.  Hint: check what the following
    # command does: curl -o /dev/null -s -w %{time_total} google.com
    # Now use the curl command to fetch webpage from the webserver you
    # spawned on host h1 (not from google!)
    # Hint: have a separate function to do this and you may find the
    # loop below useful.
    start_time = time()
    time_measures_h1 = []
    time_measures_h2 = []
    time_measures_h3 = []
    time_measures_h4 = []
    while True:
        # do the measurement (say) 3 times.
        now = time()
        delta = now - start_time
        queueSize = args.maxq
        if delta > args.time:
            break
        print ("%.1fs left..." % (args.time - delta))

        h1 = net.get('h1')
        h2 = net.get('h2')
        h3 = net.get('h3')
        h4 = net.get('h4')

        s1 = net.get('s1')
        s2 = net.get('s2')
        s3 = net.get('s3')
        s4 = net.get('s4')
        for i in range(3):
            webpage_time_h1 = h1.popen('curl -o /dev/null -s -w %%{time_total} %s/http/index.html' %
                    s1.IP()).communicate()[0]
            time_measures_h1.append(float(webpage_time_h1))

            webpage_time_h2 = h2.popen('curl -o /dev/null -s -w %%{time_total} %s/http/index.html' %
                    s2.IP()).communicate()[0]
            time_measures_h2.append(float(webpage_time_h2))

            webpage_time_h3 = h3.popen('curl -o /dev/null -s -w %%{time_total} %s/http/index.html' %
                    s3.IP()).communicate()[0]
            time_measures_h3.append(float(webpage_time_h3))

            webpage_time_h4 = h4.popen('curl -o /dev/null -s -w %%{time_total} %s/http/index.html' %
                    s4.IP()).communicate()[0]
            time_measures_h4.append(float(webpage_time_h4))
        sleep(5)
        queueSize -= 10
        switch1 = net.get('r1')
        switch2 = net.get('r2')
        net.delLinkBetween(switch1, switch2)
        net.addLink(switch1, switch2, bw=args.bw_net, delay=args.delay,
                    max_queue_size=queueSize)
        net.pingAll()

    # TODO: compute average (and standard deviation) of the fetch
    # times.  You don't need to plot them.  Just note it in your
    # README and explain.
    with open('%s/avgsd.txt'%(args.dir), 'w') as f:
        f.write(str(time_measures_h1))
        f.write(str(time_measures_h2))
        f.write(str(time_measures_h3))
        f.write(str(time_measures_h4))

    #stop_tcpprobe()
    if qmon1 is not None:
        qmon1.terminate()
    if qmon2 is not None:
        qmon2.terminate()
    net.stop()
    # Ensure that all processes you create within Mininet are killed.
    # Sometimes they require manual killing.
    Popen("pgrep -f webserver.py | xargs kill -9", shell=True).wait()

if __name__ == "__main__":
    bufferbloat()
