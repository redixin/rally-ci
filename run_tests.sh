#!/bin/sh

PY='py34'
DIR=".tox/${PY}/bin"

if [ ! -d "$DIR" ]; then
    tox -e${PY}
fi

${DIR}/flake8 &&\
${DIR}/python -m unittest discover tests/unit &&\
${DIR}/python -m unittest discover tests/async
