#!/bin/sh

.tox/py34/bin/flake8 &&\
.tox/py34/bin/python -m unittest discover tests/unit
