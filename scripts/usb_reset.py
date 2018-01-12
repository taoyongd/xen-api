#!/usr/bin/env python
#
# Copyright (C) Citrix Systems Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation; version 2.1 only. #
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
# ./usb_reset.py device -r -d dom-id -p pid
# ./usb_reset.py 2-2 -r -d 12 -p 4130
# 1. reset device
# 2. if it's the first USB device to pass-through
#      a) bind mount /dev /sys in chroot directory (/var/xen/qemu/<domid))
#      b) create and join cgroup devices:/qemu-<domid>,
#      c) blacklist all and add default device whitelist,
# 3. set device file uid/gid to (qemu_base + dom-id)
# 4. add current device to whitelist
#
# ./usb_reset.py device -i uid gid
# ./usb_reset.py 2-2 -i 0 0
# 1. restore device file owner to uid/gid
# 2. remove current device from whitelist

from stat import S_ISCHR, S_ISBLK
import argparse
from subprocess import check_call
import fcntl
import grp
import xcp.logger as log
import logging
import os
import pwd
import re
import traceback


#USBDEVFS_RESET _IO('U', 20)
USBDEVFS_RESET = (ord('U') << 8) | 20


def parse_arg():
    parser = argparse.ArgumentParser(
        description="script to reset, change owner of usb device")
    parser.add_argument("device", help="the target device")
    parser.add_argument("-p", dest="pid", type=int,
                        help="the process id of QEMU")
    parser.add_argument("-r", dest="reset", action="store_true",
                        help="reset usb device")
    perm = parser.add_mutually_exclusive_group()
    perm.add_argument("-d", dest="dom_id", type=int,
                      help="change ownership by dom_id")
    perm.add_argument("-i", dest="id", type=int, nargs=2,
                      help="change ownership by uid gid")
    return parser.parse_args()


def read_int(path):
    with open(path) as f:
        return int(f.readline())


def dev_path(bus, dev):
    return "/dev/bus/usb/{0:03d}/{1:03d}".format(bus, dev)


def reset_device(path):
    with open(path, "w") as f:
        fcntl.ioctl(f.fileno(), USBDEVFS_RESET, 0)


def domid_to_ids(dom_id):
    return pwd.getpwnam("qemu_base").pw_uid + dom_id, grp.getgrnam(
        "qemu_base").gr_gid + dom_id


def get_dev_control(path, mode):
    try:
        st = os.stat(path)
    except OSError:
        return None
    t = ""
    if S_ISBLK(st.st_mode):
        t = "b "
    elif S_ISCHR(st.st_mode):
        t = "c "
    if t and (mode == "r" or mode == "rw"):
        return t + str(os.major(st.st_rdev)) + ":" + str(os.minor(
            st.st_rdev)) + " " + mode
    return None


def get_cg_dir(dom_id):
    return "/sys/fs/cgroup/devices/qemu-{}/".format(dom_id)


def create_and_join_cgroup(dom_id, pid):
    cg_dir = get_cg_dir(dom_id)
    try:
        os.mkdir(cg_dir, 0755)
        with open(cg_dir + "tasks", "w", 0) as tasks, \
                open(cg_dir + "devices.deny", "w", 0) as deny, \
                open(cg_dir + "devices.allow", "w", 0) as allow:

            # deny all by default
            deny.write("a")

            # SM backend, this won't be necessary after QEMU startwith -S
            allow.write("b 254:* rw")

            whitelist = [
                ("/dev/urandom", "r"),
                ("/dev/xen/privcmd", "rw"),
                ("/dev/net/tun", "rw"),
                #   ("/dev/ptmx", "rw"),
                ("/dev/xen/evtchn", "rw"),
                ("/dev/mem", "rw"),
                ("/dev/null", "r")
                # "/dev/sm/backend/"
                # "/dev/pts/*"
            ]
            # for path in sm_paths:
            #     whitelist.append((path, "rw"))
            for dev in whitelist:
                control = get_dev_control(*dev)
                if control:
                    allow.write(control)

            tasks.write(str(pid))

    except OSError:
        log.debug(traceback.format_exc())
        exit(1)


def allow_device(dom_id, path):
    cg_dir = get_cg_dir(dom_id)
    with open(cg_dir + "devices.allow", "w", 0) as allow:
        control = get_dev_control(path, "rw")
        if control:
            allow.write(control)


def deny_device(dom_id, path):
    cg_dir = get_cg_dir(dom_id)
    with open(cg_dir + "devices.deny", "w", 0) as deny:
        control = get_dev_control(path, "rw")
        if control:
            deny.write(control)


if __name__ == "__main__":
    log.logToSyslog(level=logging.DEBUG)

    arg = parse_arg()
    device = arg.device
    pattern = re.compile(r"^\d+-\d+(\.\d+)*$")
    if pattern.match(device) is None:
        log.debug("unexpected device node: {}".format(device))
        exit(1)

    try:
        bus = read_int("/sys/bus/usb/devices/{}/busnum".format(device))
        dev = read_int("/sys/bus/usb/devices/{}/devnum".format(device))
        path = dev_path(bus, dev)

        if arg.reset:
            reset_device(path)

    except (IOError, ValueError):
        log.debug(traceback.format_exc())
        exit(1)

    try:
        if arg.dom_id:
            os.chown(path, *domid_to_ids(arg.dom_id))
        elif arg.id and len(arg.id) == 2:
            os.chown(path, arg.id[0], arg.id[1])

    except OSError:
        log.debug(traceback.format_exc())
        exit(1)

    root_dir = "/var/xen/qemu/{}/".format(arg.dom_id)
    if not os.path.isdir(root_dir) or not os.path.isdir(root_dir + "dev/"):
        log.debug(traceback.format_exc())
        exit(1)

    mount = "/usr/bin/mount"
    if arg.pid:
        if not os.path.isdir(root_dir + "dev/bus/"):
            # first USB device to pass-through
            check_call([mount, "-o", "bind", "/dev", root_dir + "dev/"])
            create_and_join_cgroup(arg.dom_id, arg.pid)

        if not os.path.isdir(root_dir + "sys/"):
            os.mkdir(root_dir + "sys/", 0755)
            check_call([mount, "-t", "sysfs", "sys", root_dir + "sys/"])

        allow_device(arg.dom_id, path)

    else:
        deny_device(arg.dom_id, path)
