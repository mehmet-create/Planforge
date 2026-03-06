from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blueprints", "0002_blueprint_uuid"),
    ]

    operations = [
        migrations.AlterField(
            model_name="blueprint",
            name="is_complete",
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
