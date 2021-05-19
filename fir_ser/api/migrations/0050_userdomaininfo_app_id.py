# Generated by Django 3.0.3 on 2021-05-19 18:15

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0049_remove_userinfo_domain_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='userdomaininfo',
            name='app_id',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='api.Apps',
                                    verbose_name='APP专属域名'),
        ),
    ]