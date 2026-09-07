from django.core.management.base import BaseCommand

from repayments import services


class Command(BaseCommand):
    """정산일이 된, 아직 미분배 상환건을 투자자에게 분배한다. cron 등 외부 스케줄러로 주기 실행."""

    help = '정산일(due_date)이 지난 미분배 상환건을 투자자에게 분배한다.'

    def handle(self, *args, **options):
        settled = services.distribute_due_repayments()
        self.stdout.write(f'{len(settled)}건을 분배했습니다.')
