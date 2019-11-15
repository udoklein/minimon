#!/usr/bin/python
# -*- coding: utf-8 -*-

LICENSE = """
Copyright 2019 Udo Klein - http://www.blinkenlight.net

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

VERSION = "1.0.1"

import serial
import serial.tools.list_ports as list_ports
import sys
import collections
import argparse
import time
import hexdump
import threading
import os
import Queue

# proper handling of pipe failure during output
# https://stackoverflow.com/questions/14207708/ioerror-errno-32-broken-pipe-python
from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE, SIG_DFL)

Port = collections.namedtuple("Port", ["path", "description", "hardware"])
default_port = Port("/dev/ttyUSB0", "USB0", "unknown hardware")
default_baudrate = 57600

# determine "interesting" serial ports
# that is ports with a hardware description
# those are the ones that might be connected with a usb serial bridge
ports = [Port(path, description, hardware) for path, description, hardware in list_ports.comports() if hardware != "n/a"]
if ports:
    default_port = ports[0]


parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                 description="Simple serial port monitor")

parser.add_argument("-V", "--version", action="store_true",
                    help="version")

parser.add_argument("--license", action="store_true",
                    help="license")

port_group = parser.add_mutually_exclusive_group()
port_group.add_argument("-p", "--port", type=str, default=default_port.path,
                    help="port")

port_group.add_argument("-pp", "-P", "--PortPattern", type=str,
                    help="grep for portname")

parser.add_argument("-b", "--baudrate", type=int, default=default_baudrate,
                    help="baudrate")

list_group = parser.add_mutually_exclusive_group()
list_group.add_argument("-l", "--list", action="store_true",
                        help="list ports that have a hardware description")

list_group.add_argument("-L", "--List", action="store_true",
                        help="list all ports")

parser.add_argument("-x", "--hex", action="store_true",
                    help="hexdump mode")

timestamp_group = parser.add_mutually_exclusive_group()
timestamp_group.add_argument("-t", "--timestamp", action="store_true",
                             help="timestamp (UTC)")

timestamp_group.add_argument("-ts", "--short_timestamp", action="store_true",
                             help="short timestamp (UTC)")

parser.add_argument("-n", "--newline", choices=["pass", "cr", "lf", "crlf", "none"], default='pass',
                    help="newline handling, pass='do nothing', everything else: map newlines accordingly")

parser.add_argument("-dtr", "--DTR", action="store_true",
                    help="toggle DTR to 1 on startup, wait and toggle back to 0, useful to trigger Arduino resets")

parser.add_argument("-v", "--verbose", action="store_true",
                    help="verbose")


def show_ports(long):
    ports = [Port(path, description.strip(), hardware) for path, description, hardware in list_ports.comports() if long or hardware != "n/a"]
    for port in ports:
        print "{path} ({description}, {hardware})".format(**port._asdict())
    print

early_exit = False
args = parser.parse_args()

if args.verbose:
    print args

if args.List:
    show_ports(long=True)
    early_exit = True

if args.list:
    show_ports(long=False)
    early_exit = True

if args.license:
    print LICENSE
    early_exit = True

if args.version:
    print os.path.basename(__file__), "running as", sys.argv[0]
    print "Version: ",
    print VERSION
    early_exit = True

if early_exit:
    sys.exit()

if args.PortPattern:
    import re
    pattern = re.compile(args.PortPattern)
    port, = [port.path for port in ports if pattern.search(port.path)] or [None]
    if not port:
        print "no port found for pattern {0}".format(args.PortPattern)
        sys.exit(-1)
else:
    port = args.port


now = lambda: False
if args.timestamp:
    from datetime import datetime
    now = datetime.utcnow

if args.short_timestamp:
    from datetime import datetime
    now = lambda: datetime.utcnow().strftime("%H:%M:%S.%f")


try:
    ser = serial.Serial(args.port, args.baudrate, dsrdtr=True)
    if args.DTR:
        ser.setDTR(1)
        time.sleep(0.25)
        ser.setDTR(0)

    def read(queue):
        try:
            while True:
                s = ser.read(16) if args.hex else ser.readline()
                queue.put((s, now()))
        except serial.SerialException as ex:
            print ex
            os._exit(1)

    def write(queue):
        while True:
            s, now = queue.get()
            if now:
                print now,
            if args.hex:
                hexdump.hexdump(s)
            else:
                print(s),
            sys.stdout.flush()


    queue = Queue.Queue()

    thread = threading.Thread(target=write, args=[queue])
    thread.daemon = True
    thread.start()

    thread = threading.Thread(target=read, args=[queue])
    thread.daemon = True
    thread.start()


    newline_suffix = {
        "pass": None,
        "cr":   "\r",
        "lf":   "\n",
        "crlf": "\r\n",
        "none": ""
    }[args.newline]
    while True:
        line = sys.stdin.readline()
        cooked_line = line if newline_suffix == None else line.rstrip() + newline_suffix
        ser.write(cooked_line)

except IOError as ex:
    print ex
    os._exit(1)
except KeyboardInterrupt:
    sys.exit()