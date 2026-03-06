import uuid
from django.db import migrations, models


def backfill_uuids(apps, schema_editor):
    """
    Existing rows may have duplicate or null UUIDs.
    Assign a fresh unique UUID to every row before the unique index is created.
    """
    BlueprintMessage = apps.get_model("blueprints", "BlueprintMessage")
    for msg in BlueprintMessage.objects.all():
        msg.uuid = uuid.uuid4()
        msg.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("blueprints", "0003_blueprint_is_complete_index"),
    ]

    operations = [
        # Step 1 — add the column without unique constraint so it can hold
        # whatever values are already in the DB (nulls or duplicates).
        migrations.AddField(
            model_name="blueprintmessage",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                null=True,          # allow nulls during backfill
            ),
        ),

        # Step 2 — give every existing row its own unique UUID.
        migrations.RunPython(backfill_uuids, reverse_code=migrations.RunPython.noop),

        # Step 3 — tighten the column: not null, unique, indexed.
        migrations.AlterField(
            model_name="blueprintmessage",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                null=False,
                unique=True,
                db_index=True,
            ),
        ),
    ]