from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Count, QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from .models import (
    Attachment,
    EkModifier,
    Partner,
    StockMovement,
    StockMovementDetail,
    TaxRate,
)
from .serializers import (
    AttachmentSerializer,
    EkModifierSerializer,
    PartnerSerializer,
    StockMovementDetailSerializer,
    StockMovementListSerializer,
    StockMovementSerializer,
    TaxRateSerializer,
)


class PartnerViewSet(viewsets.ModelViewSet[Partner]):
    queryset = Partner.objects.all()
    serializer_class = PartnerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Partner]:
        qs = Partner.objects.all()
        partner_type = self.request.query_params.get('partner_type')
        if partner_type:
            qs = qs.filter(partner_type=partner_type)
        return qs


class TaxRateViewSet(viewsets.ModelViewSet[TaxRate]):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    permission_classes = [IsAuthenticated]


class StockMovementViewSet(viewsets.ModelViewSet[StockMovement]):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self) -> type[BaseSerializer[StockMovement]]:
        if self.action == 'list':
            return StockMovementListSerializer
        return StockMovementSerializer

    def get_queryset(self) -> QuerySet[StockMovement]:
        qs = StockMovement.objects.select_related(
            'partner', 'period').prefetch_related('details__tax_rate').annotate(
            attachment_count=Count('attachments', distinct=True)
        )
        period_id = self.request.query_params.get('period_id')
        movement_type = self.request.query_params.get('movement_type')
        if period_id:
            qs = qs.filter(period_id=period_id)
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        partner_id = self.request.query_params.get('partner_id')
        if partner_id:
            qs = qs.filter(partner_id=partner_id)
        date = self.request.query_params.get('date')
        if date:
            qs = qs.filter(date=date)
        article_ids = self.request.query_params.getlist('article_id')
        if article_ids:
            qs = qs.filter(details__article__in=article_ids).distinct()
        return qs

    def perform_create(self, serializer: BaseSerializer[StockMovement]) -> None:
        serializer.save()

    @action(detail=True, methods=['post'])
    def apply_discount(self, request: Request, pk: int | None = None) -> Response:
        movement = self.get_object()
        percent = request.data.get('percent')
        if percent is None:
            return Response({'error': 'percent required'}, status=status.HTTP_400_BAD_REQUEST)
        movement.apply_skonto(float(percent))
        return Response(StockMovementSerializer(movement, context={'request': request}).data)


class StockMovementDetailViewSet(viewsets.ModelViewSet[StockMovementDetail]):
    serializer_class = StockMovementDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[StockMovementDetail]:
        movement_pk = self.kwargs.get('movement_pk')
        return StockMovementDetail.objects.filter(
            stock_movement_id=movement_pk
        ).select_related('article', 'tax_rate')


class EkModifierViewSet(viewsets.ModelViewSet[EkModifier]):
    serializer_class = EkModifierSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[EkModifier]:
        qs = EkModifier.objects.all()
        period_id = self.request.query_params.get('period_id')
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs


ACCEPTED_MIME_PREFIXES = ('image/',)
ACCEPTED_MIME_TYPES = ('application/pdf',)


class AttachmentViewSet(viewsets.ModelViewSet[Attachment]):
    serializer_class = AttachmentSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self) -> QuerySet[Attachment]:
        movement_pk = self.kwargs.get('movement_pk')
        return Attachment.objects.filter(stock_movement_id=movement_pk)

    def create(self, request: Request, movement_pk: int) -> Response:
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'Keine Datei hochgeladen.'}, status=status.HTTP_400_BAD_REQUEST)

        content_type: str = uploaded_file.content_type or ''
        is_pdf = content_type == 'application/pdf' or uploaded_file.name.lower().endswith('.pdf')
        is_image = any(content_type.startswith(p) for p in ACCEPTED_MIME_PREFIXES)

        if not (is_pdf or is_image):
            return Response(
                {'error': 'Nur Bilder und PDFs sind erlaubt.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        movement = StockMovement.objects.get(pk=movement_pk)
        filename: str = uploaded_file.name or 'upload'

        if is_pdf:
            attachments = self._process_pdf(movement, uploaded_file, filename)
        else:
            attachment = Attachment(
                stock_movement=movement,
                original_filename=filename,
            )
            attachment.file = uploaded_file
            attachment.save()
            attachments = [attachment]

        serializer = AttachmentSerializer(attachments, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _process_pdf(
        self,
        movement: StockMovement,
        uploaded_file: object,
        filename: str,
    ) -> list[Attachment]:
        import pymupdf

        pdf_bytes: bytes = uploaded_file.read()  # type: ignore[attr-defined]
        doc: pymupdf.Document = pymupdf.open(stream=pdf_bytes, filetype='pdf')
        attachments: list[Attachment] = []
        stem = filename.rsplit('.', 1)[0]

        for page_num in range(len(doc)):
            page: pymupdf.Page = doc[page_num]
            pix: pymupdf.Pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            png_data: bytes = pix.tobytes('png')

            image_name = f"{stem}_seite_{page_num + 1}.png"
            image_file = SimpleUploadedFile(image_name, png_data, content_type='image/png')

            attachment = Attachment(
                stock_movement=movement,
                original_filename=image_name,
                source_filename=filename,
                page_number=page_num + 1,
            )
            attachment.file = image_file
            attachment.save()
            attachments.append(attachment)

        doc.close()
        return attachments
