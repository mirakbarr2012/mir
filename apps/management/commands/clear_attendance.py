from django.core.management.base import BaseCommand
from apps.models import Attendance

class Command(BaseCommand):
    help = 'Barcha saqlangan davomatlarni ochirib tashlaydi'

    def handle(self, *args, **options):
        count, _ = Attendance.objects.all().delete()
        self.stdout.write(
            self.style.SUCCESS(f"✓ {count} ta davomat o'chirib tashlandi")
        )
