from typing import Any

from rest_framework import serializers

from .models import Address, Customer, Department, Location, Period, UserPreferences


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Period
        fields: list[str] = ['id', 'name', 'checkpoint_year', 'start', 'end']


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields: list[str] = ['id', 'name']


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields: list[str] = ['id', 'name']


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields: list[str] = ['language', 'theme', 'period_colors']


class AddressSerializer(serializers.ModelSerializer[Address]):
    display_name = serializers.CharField(read_only=True)
    postal_label = serializers.CharField(read_only=True)
    has_name = serializers.BooleanField(read_only=True)
    customer_display = serializers.CharField(
        source='customer.display_name', read_only=True, default=None)

    class Meta:
        model = Address
        fields = [
            'id', 'wz_source_id', 'display_name', 'postal_label', 'has_name',
            'customer', 'customer_display',
            'anrede', 'vorname', 'nachname', 'firma', 'abteilung',
            'strasse', 'plz', 'ort', 'telefon', 'email', 'uid', 'anmerkung',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'wz_source_id', 'display_name', 'postal_label', 'has_name',
            'customer_display',
            'created_at', 'updated_at',
        ]


class CustomerSerializer(serializers.ModelSerializer[Customer]):
    display_name = serializers.CharField(read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)
    # Annotated by CustomerViewSet.get_queryset; falls back to the property when
    # the instance comes from somewhere else (e.g. a create response).
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'id', 'wz_source_id', 'customer_number', 'name', 'display_name',
            'default_address', 'addresses',
            'email', 'telefon', 'uid', 'notes', 'is_active', 'balance',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'wz_source_id', 'customer_number', 'display_name',
            'addresses', 'balance', 'created_at', 'updated_at',
        ]

    def get_balance(self, obj: Customer) -> str:
        annotated = getattr(obj, 'balance_sum', None)
        if annotated is not None:
            return str(annotated)
        # Imported lazily: core must not depend on billing at module level.
        from billing.services.ledger import customer_balance
        return str(customer_balance(obj))

    def validate_default_address(self, value: Address | None) -> Address | None:
        """The default address must be one of this customer's own addresses."""
        if value is None:
            return value
        instance: Customer | None = getattr(self, 'instance', None)
        if instance is None or value.customer_id != instance.pk:
            raise serializers.ValidationError(
                'Die Standardadresse muss eine Adresse dieses Kunden sein.')
        return value


class CustomerLedgerEntryReadSerializer(serializers.Serializer[Any]):
    """Read-only shape of GET /customers/{id}/ledger/ — see CustomerViewSet.ledger."""
    id = serializers.IntegerField()
    entry_date = serializers.DateField()
    entry_type = serializers.CharField()
    entry_type_display = serializers.CharField()
    description = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    running_balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    invoice = serializers.IntegerField(allow_null=True)
    invoice_number = serializers.CharField(allow_null=True)
    reminder = serializers.IntegerField(allow_null=True)
    reminder_number = serializers.CharField(allow_null=True)
    is_reversal = serializers.BooleanField()
    actor = serializers.CharField(allow_null=True)


class SyncWzSerializer(serializers.Serializer[Any]):
    """Request body for WZ address sync."""
    host = serializers.CharField()
    database = serializers.CharField()
    user = serializers.CharField()
    password = serializers.CharField()
