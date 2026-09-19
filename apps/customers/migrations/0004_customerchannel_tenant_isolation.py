# Tenant isolation for CustomerChannel: unique per (workspace, channel, external_id)

import django.db.models.deletion
from django.db import migrations, models


def backfill_channel_workspace(apps, schema_editor):
    """Populate workspace from the owning customer for existing rows.

    Done in Python rather than a subquery — the row count here is small
    (one row per channel identity) and it avoids self-referencing UPDATEs.
    """
    CustomerChannel = apps.get_model("customers", "CustomerChannel")
    for channel in CustomerChannel.objects.select_related("customer").all():
        channel.workspace_id = channel.customer.workspace_id
        channel.save(update_fields=["workspace"])


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0003_alter_customerchannel_profile_url"),
        ("workspaces", "0001_initial"),
    ]

    operations = [
        # 1. Drop the old global uniqueness (channel + external_id)
        migrations.RemoveIndex(
            model_name="customerchannel",
            name="customer_ch_channel_ee6e37_idx",
        ),
        migrations.AlterUniqueTogether(
            name="customerchannel",
            unique_together=set(),
        ),
        # 2. Add workspace FK (nullable during backfill)
        migrations.AddField(
            model_name="customerchannel",
            name="workspace",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="customer_channels",
                to="workspaces.workspace",
            ),
        ),
        # 3. Backfill workspace from the customer relation
        migrations.RunPython(
            backfill_channel_workspace,
            reverse_code=migrations.RunPython.noop,
        ),
        # 4. Enforce non-null + new compound uniqueness
        migrations.AlterField(
            model_name="customerchannel",
            name="workspace",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="customer_channels",
                to="workspaces.workspace",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="customerchannel",
            unique_together={("workspace", "channel", "external_id")},
        ),
        migrations.AddIndex(
            model_name="customerchannel",
            index=models.Index(
                fields=["workspace", "channel", "external_id"],
                name="customer_ch_workspa_006b01_idx",
            ),
        ),
    ]
