#!/usr/bin/env bash

if [ -z "$1" ]; then
  N=1
else
  N=$1
fi

while (( N >= 1))
do
  ./init-repo.sh $N
  (( N-- ))
done

./init-hybrid.sh
