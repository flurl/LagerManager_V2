from core.permissions import DjangoModelPermissionsWithView, require_perm
from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Article,
    ArticleGroup,
    ArticleMeta,
    Recipe,
    WarehouseArticle,
    WarehouseUnit,
)
from .serializers import (
    ArticleGroupSerializer,
    ArticleMetaSerializer,
    ArticleSerializer,
    RecipeSerializer,
    WarehouseArticleSerializer,
    WarehouseUnitSerializer,
)
from .services.mssql_import import run_import
from .services.wz_invoice_import import (
    get_aufwand_checkpoints,
    get_aufwand_tische,
    get_tisch_aufwand_lines,
)


class ArticleMetaViewSet(viewsets.ModelViewSet[ArticleMeta]):
    """CRUD for per-article metadata scoped to a period."""
    serializer_class = ArticleMetaSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> QuerySet[ArticleMeta]:
        qs = ArticleMeta.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class ArticleGroupViewSet(viewsets.ReadOnlyModelViewSet[ArticleGroup]):
    serializer_class = ArticleGroupSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> QuerySet[ArticleGroup]:
        qs = ArticleGroup.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class ArticleViewSet(viewsets.ReadOnlyModelViewSet[Article]):
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> QuerySet[Article]:
        qs = Article.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs.select_related('period')


class RecipeViewSet(viewsets.ReadOnlyModelViewSet[Recipe]):
    serializer_class = RecipeSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> QuerySet[Recipe]:
        qs = Recipe.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class WarehouseUnitViewSet(viewsets.ReadOnlyModelViewSet[WarehouseUnit]):
    serializer_class = WarehouseUnitSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> QuerySet[WarehouseUnit]:
        qs = WarehouseUnit.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


class WarehouseArticleViewSet(viewsets.ReadOnlyModelViewSet[WarehouseArticle]):
    serializer_class = WarehouseArticleSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> QuerySet[WarehouseArticle]:
        qs = WarehouseArticle.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs.select_related('article')


class WzInvoiceImportView(APIView):
    """
    Three read-only endpoints for the WZ → Invoice import dialog.

    GET /api/wz-import/checkpoints/?period_id=
    GET /api/wz-import/tische/?period_id=&checkpoint_id=
    GET /api/wz-import/bondetails/?period_id=&tisch_id=
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, resource: str) -> Response:
        period_id_raw = request.query_params.get('period_id')
        if not period_id_raw:
            return Response({'error': 'period_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            period_id = int(period_id_raw)
        except ValueError:
            return Response({'error': 'period_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        if resource == 'checkpoints':
            qs = get_aufwand_checkpoints(period_id)
            data = [
                {
                    'id': cp.source_id,
                    'datum': cp.datum.date().isoformat(),
                    'label': cp.info if cp.info else cp.datum.date().isoformat(),
                }
                for cp in qs
            ]
            return Response(data)

        if resource == 'tische':
            checkpoint_id_raw = request.query_params.get('checkpoint_id')
            if not checkpoint_id_raw:
                return Response({'error': 'checkpoint_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                checkpoint_id = int(checkpoint_id_raw)
            except ValueError:
                return Response({'error': 'checkpoint_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
            return Response(get_aufwand_tische(period_id, checkpoint_id))

        if resource == 'bondetails':
            tisch_id_raw = request.query_params.get('tisch_id')
            if not tisch_id_raw:
                return Response({'error': 'tisch_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                tisch_id = int(tisch_id_raw)
            except ValueError:
                return Response({'error': 'tisch_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
            return Response(get_tisch_aufwand_lines(period_id, tisch_id))

        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)


class ImportRunView(APIView):
    """
    POST /api/import/run/
    Body: {period_id, host, database, user, password}
    Runs the MSSQL import synchronously; returns when complete.
    """
    permission_classes = [IsAuthenticated, require_perm('core.run_import')]

    def post(self, request: Request) -> Response:
        period_id = request.data.get('period_id')
        host = request.data.get('host', '')
        database = request.data.get('database', '')
        user = request.data.get('user', '')
        password = request.data.get('password', '')

        if period_id is None or not host or not database or not user:
            return Response(
                {'error': 'period_id, host, database, user are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            summary = run_import(int(period_id), host,
                                 database, user, password)
            return Response({'status': 'ok', 'summary': summary})
        except Exception as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
