from django.apps import AppConfig

class MoviesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Movies'

    def ready(self):
        import os
        # Only start scheduler if DATABASE_URL is set (i.e. on Render)
        if os.environ.get('DATABASE_URL'):
            from Movies.scheduler import start
            start()