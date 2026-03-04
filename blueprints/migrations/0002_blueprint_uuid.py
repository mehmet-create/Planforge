import uuid
from django.db import migrations, models


def gen_uuid(apps, schema_editor):
    Blueprint = apps.get_model("blueprints", "Blueprint")
    for bp in Blueprint.objects.all():
        bp.uuid = uuid.uuid4()
        bp.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("blueprints", "0001_initial"),
    ]

    operations = [
        # Step 1 — add the column without unique constraint, nullable so existing rows don't fail
        migrations.AddField(
            model_name="blueprint",
            name="uuid",
            field=models.UUIDField(null=True),
        ),
        # Step 2 — fill every existing row with its own unique UUID
        migrations.RunPython(gen_uuid, migrations.RunPython.noop),
        # Step 3 — now safe to add unique + not null
        migrations.AlterField(
            model_name="blueprint",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True),
        ),
    ]