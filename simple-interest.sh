#!/bin/bash

# Script to calculate simple interest

# inputs
p=$1
r=$2
t=$3

si=$(( (p*r*t) / 100 ))

echo "The simple interest is: $si"
