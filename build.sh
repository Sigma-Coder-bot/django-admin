#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --fake Movies 0006_genre_language_movie_genres_movie_language_and_more
python manage.py migrate
python manage.py createsu