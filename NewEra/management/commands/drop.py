from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
# from blogapp.models import Resource

# DROP SCRIPT

class Command(BaseCommand):
    args = '<this func takes no args>'
    help = 'Run this script to create sample users.'

    def _destroy_users(self):
        users = User.objects.all()

        for u in users:
            u.delete() 

    def handle(self, *args, **options):
        self._destroy_users()