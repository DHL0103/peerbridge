from django.db import migrations

PLATFORM_USERNAME = 'platform'


def create_platform_account(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.get_or_create(
        username=PLATFORM_USERNAME,
        defaults={'email': 'platform@peerbridge.internal', 'is_active': False, 'password': '!'},
    )


def remove_platform_account(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(username=PLATFORM_USERNAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_bankaccount_options'),
    ]

    operations = [
        migrations.RunPython(create_platform_account, remove_platform_account),
    ]
