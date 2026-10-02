"""Wait for one private pre-dispatch byte, then exec the approved exact argv.

No lifecycle/configuration policy is implemented here. The reviewed caller owns
that policy and records this child's actual birth before releasing the pipe.
"""
import os
import sys


def main():
    if len(sys.argv) < 3:
        raise ValueError('gate requires inherited FD and exact argv')
    fd = int(sys.argv[1])
    argv = sys.argv[2:]
    if fd < 3 or not argv[0].startswith('/') or any('\0' in v for v in argv):
        raise ValueError('invalid finite gate arguments')
    os.set_inheritable(fd, False)
    try:
        release = os.read(fd, 2)
    finally:
        os.close(fd)
    if release != b'G':
        raise ValueError('gate closed without exact dispatch release')
    os.execvpe(argv[0], argv, os.environ)


if __name__ == '__main__':
    main()
