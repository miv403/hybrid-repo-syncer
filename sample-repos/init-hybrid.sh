#!/usr/bin/env bash

mkdir hybrid
[ $? -eq 1 ] && exit 1

if [ -z "$1" ]; then
  N=1
else
  N=$1
fi

cd hybrid && git init
git config receive.denyCurrentBranch updateInstead
touch .gitignore && git add . && git commit -m "hybrid::initial commit"

if [ ! -d "../repo-$N" ];
then
  echo "repo-$N doesn't exists"
  exit 1
fi

git remote add "repo-$N-origin" "../repo-$N.git"
git remote add "repo-$N-clone" "../repo-$N"
