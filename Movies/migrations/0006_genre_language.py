from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Movies', '0005_seatreservation_alter_booking_booked_at_and_more'),  # ← fixed
    ]

    operations = [
        migrations.CreateModel(
            name='Genre',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=100, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Language',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=100, unique=True)),
            ],
        ),
        migrations.AddField(
            model_name='movie',
            name='language',
            field=models.ForeignKey(
                blank=True, db_index=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='movies', to='Movies.language'
            ),
        ),
        migrations.AddField(
            model_name='movie',
            name='genres',
            field=models.ManyToManyField(
                blank=True, related_name='movies', to='Movies.genre'
            ),
        ),
    ]