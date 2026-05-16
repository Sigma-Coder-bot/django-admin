#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --fake Movies 0001_initial
python manage.py migrate
python manage.py createsu