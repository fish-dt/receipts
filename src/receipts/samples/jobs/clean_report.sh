#!/bin/bash
# schedule: 0 2 * * *
# tz: UTC
n=$(wc -l < input.txt)
echo "lines=$n"
