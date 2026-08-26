from django.core.management.base import BaseCommand

from loans import services


class Command(BaseCommand):
    """마감일 지난 모집중 대출을 취소하고 투자자에게 환불한다. cron 등 외부 스케줄러로 주기 실행."""

    help = '마감일이 지났는데 목표 금액을 못 채운 대출을 취소하고 투자자에게 전액 환불한다.'

    def handle(self, *args, **options):
        cancelled = services.expire_fundraising_loans()
        self.stdout.write(f'{len(cancelled)}건의 대출을 취소했습니다.')
