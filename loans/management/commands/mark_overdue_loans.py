from django.core.management.base import BaseCommand

from loans import services


class Command(BaseCommand):
    """상환일 지난 대출을 연체 일수에 따라 OVERDUE_1/OVERDUE_2/DEFAULT로 승급한다. cron 등 외부 스케줄러로 주기 실행."""

    help = '상환일이 지난 대출을 연체 일수에 따라 자동 승급한다.'

    def handle(self, *args, **options):
        updated = services.mark_overdue_loans()
        self.stdout.write(f'{len(updated)}건의 대출 상태를 갱신했습니다.')
