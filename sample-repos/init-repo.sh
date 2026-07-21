#!/usr/bin/env bash

if [ -z "$1" ]; then
  N=1
else
  N=$1
fi

mkdir "repo-$N.git"
[ $? -eq 1 ] && exit 1
cd "repo-$N.git" && git init --bare
cd .. && git clone "repo-$N.git" "repo-$N"

cd "repo-$N" && mkdir a b
echo "file a" > a/file.a
git add a && git commit -m "added a/file.a"
echo "file b" > b/file.b
git add b && git commit -m "added b/file.b"

