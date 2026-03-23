from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.mssql_import import run_import


class ImportRunView(APIView):
    """
    POST /api/import/run/
    Body: {period_id, host, database, user, password}
    Runs the MSSQL import synchronously; returns when complete.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        period_id = request.data.get('period_id')
        host = request.data.get('host', '')
        database = request.data.get('database', '')
        user = request.data.get('user', '')
        password = request.data.get('password', '')

        if not all([period_id, host, database, user]):
            return Response(
                {'error': 'period_id, host, database, user are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            summary = run_import(int(period_id), host, database, user, password)
            return Response({'status': 'ok', 'summary': summary})
        except Exception as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
