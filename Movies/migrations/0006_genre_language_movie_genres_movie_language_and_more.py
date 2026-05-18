from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Movies', '0006_genre_language_movie_genres_movie_language_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            # Add language_id column if it doesn't exist
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='Movies_movie' AND column_name='language_id'
                    ) THEN
                        ALTER TABLE "Movies_movie"
                        ADD COLUMN "language_id" bigint NULL
                        REFERENCES "Movies_language"("id")
                        DEFERRABLE INITIALLY DEFERRED;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name='Movies_movie_genres'
                    ) THEN
                        CREATE TABLE "Movies_movie_genres" (
                            "id" bigserial NOT NULL PRIMARY KEY,
                            "movie_id" bigint NOT NULL
                                REFERENCES "Movies_movie"("id")
                                DEFERRABLE INITIALLY DEFERRED,
                            "genre_id" bigint NOT NULL
                                REFERENCES "Movies_genre"("id")
                                DEFERRABLE INITIALLY DEFERRED,
                            UNIQUE ("movie_id", "genre_id")
                        );
                    END IF;
                END
                $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]