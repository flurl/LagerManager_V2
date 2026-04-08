from core.permissions import DjangoModelPermissionsWithView
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Count, QuerySet
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from .models import (
    Attachment,
    Partner,
    StockMovement,
    StockMovementDetail,
    TaxRate,
)
from .serializers import (
    AttachmentSerializer,
    PartnerSerializer,
    StockMovementDetailSerializer,
    StockMovementListSerializer,
    StockMovementSerializer,
    TaxRateSerializer,
)


class PartnerViewSet(viewsets.ModelViewSet[Partner]):
    queryset = Partner.objects.all()
    serializer_class = PartnerSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> QuerySet[Partner]:
        qs = Partner.objects.all()
        partner_type = self.request.query_params.get('partner_type')
        if partner_type:
            qs = qs.filter(partner_type=partner_type)
        return qs


class TaxRateViewSet(viewsets.ModelViewSet[TaxRate]):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]


class StockMovementViewSet(viewsets.ModelViewSet[StockMovement]):
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

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
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]

    def get_queryset(self) -> QuerySet[StockMovementDetail]:
        movement_pk = self.kwargs.get('movement_pk')
        return StockMovementDetail.objects.filter(
            stock_movement_id=movement_pk
        ).select_related('article', 'tax_rate')


ACCEPTED_MIME_PREFIXES = ('image/',)
ACCEPTED_MIME_TYPES = ('application/pdf',)


class AttachmentViewSet(viewsets.ModelViewSet[Attachment]):
    serializer_class = AttachmentSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissionsWithView]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self) -> QuerySet[Attachment]:
        movement_pk = self.kwargs.get('movement_pk')
        if movement_pk:
            return Attachment.objects.filter(stock_movement_id=movement_pk)
        return Attachment.objects.all()

    def create(self, request: Request, movement_pk: int | None = None) -> Response:
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

        movement: StockMovement | None = StockMovement.objects.get(pk=movement_pk) if movement_pk else None
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
        movement: StockMovement | None,
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

    @action(detail=False, methods=['get'])
    def merged_pdf(self, request: Request) -> HttpResponse:
        import pymupdf

        attachment_ids: list[str] = request.query_params.getlist('attachment_id')
        if not attachment_ids:
            return Response({'error': 'Keine Anhang-IDs angegeben.'}, status=status.HTTP_400_BAD_REQUEST)

        id_list: list[int] = [int(a) for a in attachment_ids]
        attachments_by_id: dict[int, Attachment] = {
            a.pk: a for a in Attachment.objects.filter(pk__in=id_list)
        }
        # Preserve caller-supplied order
        ordered: list[Attachment] = [attachments_by_id[i] for i in id_list if i in attachments_by_id]

        if not ordered:
            return Response({'error': 'Keine Anhänge gefunden.'}, status=status.HTTP_404_NOT_FOUND)

        merged: pymupdf.Document = pymupdf.open()
        for attachment in ordered:
            img_bytes: bytes = attachment.file.read()
            img_doc: pymupdf.Document = pymupdf.open(stream=img_bytes, filetype='png')
            img_pdf_bytes: bytes = img_doc.convert_to_pdf()
            img_pdf: pymupdf.Document = pymupdf.open('pdf', img_pdf_bytes)
            merged.insert_pdf(img_pdf)
            img_doc.close()
            img_pdf.close()

        pdf_bytes: bytes = merged.tobytes()
        merged.close()

        return HttpResponse(pdf_bytes, content_type='application/pdf')
