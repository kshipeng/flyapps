# Generated by Django 3.0.3 on 2020-04-23 17:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0030_appudid_updated_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='appudid',
            name='is_signed',
            field=models.BooleanField(default=False, verbose_name='是否完成签名打包'),
        ),
    ]
