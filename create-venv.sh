#!/bin/bash -ex

script_path="$(realpath "${BASH_SOURCE[-1]}")"
script_dir="$(dirname "${script_path}")"

venv="${script_dir}/.venv"

rm -rf "${venv}"
python3 -m venv "${venv}"
source "${venv}/bin/activate"

pip install --upgrade pip

pip install \
  mypy \
  pre-commit \
  -r "${script_dir}/requirements.test.txt"
