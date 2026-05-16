from django.apps import AppConfig

class MoviesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Movies'

    def ready(self):
        import os
        if os.environ.get('DATABASE_URL'):
            # Delay scheduler start until after migrations
            from django.db import connection
            try:
                tables = connection.introspection.table_names()
                if 'django_apscheduler_djangojob' in tables:
                    from Movies.scheduler import start
                    start()
            except Exception:
                pass